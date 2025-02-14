import logging

"""
Handles deployment of an installed problem.

Deploying a problem means creating one or more instances, which are each
templated with flags, the shell server URL, etc., and assigned a port
(if required for their problem type).

Flags and assigned ports will remain consistent for (problem, instance) pairs
across any shell servers that share the SHARED_ROOT directory.

However, instances must still be created individually on each shell server,
as server URLs must be templated appropriately, dependencies potentially
need to be installed on each server, and the underlying files, users and
service definitions that make up a deployed instance are specific to each
shell server.
"""

HIGHEST_PORT = 65535
LOWEST_PORT = 1025
LOCALHOST = "127.0.0.1"

PROBLEM_FILES_DIR = "problem_files"
STATIC_FILE_ROOT = "static"
XINETD_SERVICE_PATH = "/etc/xinetd.d/"
TEMP_DEB_DIR = "/tmp/picoctf_debs/"

# will be set to the configuration module during deployment
shared_config = None
local_config = None
port_map = {}
current_problem = None
current_instance = None

logger = logging.getLogger(__name__)

def get_deploy_context():
    """
    Returns the deployment context, a dictionary containing the current
    config, port_map, problem, instance
    """

    global shared_config, local_config, port_map, current_problem, current_instance

    return {
        "shared_config": shared_config,
        "local_config": local_config,
        "port_map": port_map,
        "problem": current_problem,
        "instance": current_instance
    }


port_random = None


# checks if the port is being used by a system process
def check_if_port_in_use(port):
    import socket, errno
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        s.bind((LOCALHOST, port))
    except socket.error as e:
        return True
    s.close()
    return False


def give_port():
    """
    Returns a random port and registers it.
    """
    global port_random

    context = get_deploy_context()
    # default behavior
    if context["shared_config"] is None:
        return randint(LOWEST_PORT, HIGHEST_PORT)

    if "banned_ports_parsed" not in context["shared_config"]:
        banned_ports_result = []
        for port_range in context["shared_config"].banned_ports:
            banned_ports_result.extend(
                list(range(port_range["start"], port_range["end"] + 1)))

        context["shared_config"]["banned_ports_parsed"] = banned_ports_result

    # during real deployment, let's register a port
    if port_random is None:
        port_random = Random(context["shared_config"].deploy_secret)

    # if this instance already has a port, reuse it
    if (context["problem"], context["instance"]) in context["port_map"]:
        assigned_port = context['port_map'][(context['problem'], context['instance'])]
        logger.debug(f"This problem instance ({context['problem']}: {str(context['instance'])}) already has an assigned port: {str(assigned_port)}")
        return assigned_port

    used_ports = [port for port in context["port_map"].values() if port is not None]
    if len(used_ports) + len(
            context["shared_config"].banned_ports_parsed) == HIGHEST_PORT + 1:
        raise Exception(
            "All usable ports are taken. Cannot deploy any more instances.")

    # Added used ports to banned_ports_parsed.
    for port in used_ports:
        context["shared_config"].banned_ports_parsed.append(port)

    # in case the port chosen is in use, try again.
    loop_var = HIGHEST_PORT - len(context["shared_config"].banned_ports_parsed) + 1
    while loop_var > 0:
        # Get a random port that is random, not in the banned list, not in use, and not assigned before.
        port = port_random.choice([
            i for i in range(LOWEST_PORT, HIGHEST_PORT)
            if i not in context["shared_config"].banned_ports_parsed
        ])
        if check_if_port_in_use(port):
            loop_var -= 1
            context["shared_config"].banned_ports_parsed.append(port)
            continue
        return port
    raise Exception(
        "Unable to assigned a port to this problem. All ports are either taken or used by the system."
    )


import functools
import json
import os
import shutil
import subprocess
import traceback
from abc import ABCMeta
from ast import literal_eval
from copy import copy, deepcopy
from grp import getgrnam
from hashlib import md5, sha1
from importlib.machinery import SourceFileLoader
# These are below because of a circular import issue with problem.py and give_port
# [TODO] cleanup
from os.path import commonprefix, isdir, isfile, join
from pwd import getpwnam
from random import randint, Random
from time import sleep

from hacksport.operations import create_user, execute
from hacksport.problem import (Compiled, Directory, ExecutableFile, File,
                               FlaskApp, PHPApp, WebService, PreTemplatedFile,
                               ProtectedFile, Remote, Service)
from hacksport.status import get_all_problem_instances, get_all_problems
from jinja2 import Environment, FileSystemLoader, Template
from shell_manager.package import package_problem
from shell_manager.util import (DEPLOYED_ROOT, FatalException, get_attributes,
                                get_problem, get_problem_root,
                                sanitize_name, STAGING_ROOT, get_problem_root_hashed,
                                get_pid_hash, get_bundle, DEB_ROOT, SHARED_ROOT,
                                get_shared_config, get_local_config,
                                acquire_lock, release_lock)
from spur import RunProcessError



def challenge_meta(attributes):
    """
    Returns a metaclass that will introduce the given attributes into the class
    namespace.

    Args:
        attributes: The dictionary of attributes

    Returns:
        The metaclass described above
    """

    class ChallengeMeta(ABCMeta):

        def __new__(cls, name, bases, attr):
            attrs = dict(attr)
            attrs.update(attributes)
            return super().__new__(cls, name, bases, attrs)

    return ChallengeMeta


def update_problem_class(Class, problem_object, seed, user, instance_directory):
    """
    Changes the metaclass of the given class to introduce necessary fields before
    object instantiation.

    Args:
        Class: The problem class to be updated
        problem_name: The problem name
        seed: The seed for the Random object
        user: The linux username for this challenge instance
        instance_directory: The deployment directory for this instance

    Returns:
        The updated class described above
    """

    random = Random(seed)
    attributes = deepcopy(problem_object)

    # pass configuration options in as class fields
    attributes.update(dict(shared_config))
    attributes.update(dict(local_config))

    attributes.update({
        "random": random,
        "user": user,
        "directory": instance_directory,
        "server": local_config.hostname
    })

    return challenge_meta(attributes)(Class.__name__, Class.__bases__,
                                      Class.__dict__)


def get_username(problem_name, instance_number):
    """
    Determine the username for a given problem instance.
    """

    return "{}_{}".format(sanitize_name(problem_name), instance_number)


def create_service_files(problem, instance_number, path):
    """
    Creates xinetd service files for the given problem.
    Creates a service file for a problem

    Args:
        problem: the instantiated problem object
        instance_number: the instance number
        path: the location to drop the service file
    Returns:
        A tuple containing (service_file_path, socket_file_path).
        socket_file_path will be None if the problem is not a service.
    """

    # See https://github.com/puppetlabs/puppetlabs-xinetd/blob/master/templates/service.erb
    # and https://linux.die.net/man/5/xinetd.conf
    xinetd_template = """
service %s
{
    type = UNLISTED
    port = %d
    disable = no
    socket_type = stream
    protocol = tcp
    wait = %s
    user = %s
    group = %s
    log_type = FILE /var/log/xinetd-hacksport-%s.log
    log_on_success = HOST EXIT DURATION
    log_on_failure = HOST
    cps = 50 3
    rlimit_cpu = %s
    per_source = 100
    server = %s
}
"""

    is_service = isinstance(problem, Service)
    is_web = isinstance(problem, WebService)
    if not is_service and not is_web:
        return (None, None)

    problem_service_info = problem.service()
    service_content = xinetd_template % (
        problem.user, problem.port, "no"
        if problem_service_info["Type"] == "oneshot" else "yes", problem.user,
        problem.user, problem.user, "100"
        if problem_service_info["Type"] == "oneshot" else "UNLIMITED",
        problem_service_info['ExecStart'])

    service_file_path = join(path, "{}".format(problem.user))

    with open(service_file_path, "w") as f:
        f.write(service_content)

    return (service_file_path, None)


def create_instance_user(problem_name, instance_number):
    """
    Generates a random username based on the problem name. The username returned is guaranteed to
    not exist.

    Args:
        problem_name: The name of the problem
        instance_number: The unique number for this instance
    Returns:
        The created username
    """

    converted_name = sanitize_name(problem_name)
    username = get_username(converted_name, instance_number)

    try:
        # Check if the user already exists.
        user = getpwnam(username)
        new = False
    except KeyError:
        create_user(username)
        new = True

    return username, new


def generate_instance_deployment_directory(username):
    """
    Generates the instance deployment directory for the given username
    """

    directory = username
    if shared_config.obfuscate_problem_directories:
        directory = username + "_" + md5(
            (username + shared_config.deploy_secret).encode()).hexdigest()

    root_dir = shared_config.problem_directory_root

    if not isdir(root_dir):
        os.makedirs(root_dir)
        # make the root not world readable
        os.chmod(root_dir, 0o751)

    path = join(root_dir, directory)
    if not isdir(path):
        os.makedirs(path)

    return path


def generate_seed(*args):
    """
    Generates a seed using the list of string arguments
    """

    return md5("".join(args).encode("utf-8")).hexdigest()


def generate_staging_directory(root=STAGING_ROOT,
                               problem_name=None,
                               instance_number=None):
    """
    Creates a random, empty staging directory

    Args:
        root: The parent directory for the new directory. Defaults to join(SHARED_ROOT, "staging")

        Optional prefixes to help identify the staging directory: problem_name, instance_number

    Returns:
        The path of the generated directory
    """

    if not os.path.isdir(root):
        os.makedirs(root)

    # ensure that the staging files are not world-readable
    os.chmod(root, 0o750)

    def get_new_path():
        prefix = ""
        if problem_name is not None:
            prefix += problem_name + "_"
        if instance_number is not None:
            prefix += str(instance_number) + "_"

        path = join(root, prefix + str(randint(0, 1e16)))
        if os.path.isdir(path):
            return get_new_path()
        return path

    path = get_new_path()
    os.makedirs(path)
    return path


def template_string(template, **kwargs):
    """
    Templates the given string with the keyword arguments

    Args:
        template: The template string
        **kwards: Variables to use in templating
    """

    temp = Template(template)
    return temp.render(**kwargs)


def template_file(in_file_path, out_file_path, **kwargs):
    """
    Templates the given file with the keyword arguments.

    Args:
        in_file_path: The path to the template
        out_file_path: The path to output the templated file
        **kwargs: Variables to use in templating
    """

    env = Environment(
        loader=FileSystemLoader(os.path.dirname(in_file_path)),
        keep_trailing_newline=True)
    template = env.get_template(os.path.basename(in_file_path))
    output = template.render(**kwargs)

    with open(out_file_path, "w") as f:
        f.write(output)


def template_staging_directory(staging_directory, problem):
    """
    Templates every file in the staging directory recursively other than
    problem.json and challenge.py.

    Args:
        staging_directory: The path of the staging directory
        problem: The problem object
    """

    # prepend the staging directory to all
    dont_template = copy(problem.dont_template) + [
        "app/templates", "problem.json", "challenge.py", "templates", "__pre_templated"
    ]

    dont_template_files = list(filter(isfile, dont_template))
    dont_template_directories = list(filter(isdir, dont_template))
    dont_template_directories = [
        join(staging_directory, directory)
        for directory in dont_template_directories
    ]

    for root, dirnames, filenames in os.walk(staging_directory):
        if any(
                os.path.commonprefix([root, path]) == path
                for path in dont_template_directories):
            logger.debug(
                "....Not templating anything in the directory '{}'".format(
                    root))
            continue
        for filename in filenames:
            if filename in dont_template_files:
                logger.debug(
                    "....Not templating the file '{}'".format(filename))
                continue
            fullpath = join(root, filename)
            try:
                template_file(fullpath, fullpath, **get_attributes(problem))
            except UnicodeDecodeError as e:
                # tried templating binary file
                pass


def deploy_files(staging_directory, instance_directory, file_list, username,
                 problem_class):
    """
    Copies the list of files from the staging directory to the instance directory.
    Will properly set permissions and setgid files based on their type.
    """

    # get uid and gid for default and problem user
    user = getpwnam(username)
    default = getpwnam(shared_config.default_user)

    for f in file_list:
        # copy the file over, making the directories as needed
        output_path = join(instance_directory, f.path)
        if not os.path.isdir(os.path.dirname(output_path)):
            os.makedirs(os.path.dirname(output_path))

        if not isinstance(f, Directory):
            if isinstance(f, PreTemplatedFile):
                file_source = join(staging_directory, "__pre_templated", f.path)
            else:
                file_source = join(staging_directory, f.path)

            shutil.copy2(file_source, output_path)

        # set the ownership based on the type of file
        if isinstance(f, ProtectedFile) or isinstance(f, ExecutableFile):
            os.chown(output_path, default.pw_uid, user.pw_gid)
        else:
            uid = default.pw_uid if f.user is None else getpwnam(f.user).pw_uid
            gid = default.pw_gid if f.group is None else getgrnam(
                f.group).gr_gid
            os.chown(output_path, uid, gid)

        # set the permissions appropriately
        os.chmod(output_path, f.permissions)

    if issubclass(problem_class, Service):
        os.chown(instance_directory, default.pw_uid, user.pw_gid)
        os.chmod(instance_directory, 0o750)


def install_user_service(service_file, socket_file):
    """
    Installs the service file and socket file into the xinetd
    service directory, sets the service to start on boot, and
    starts the service now.

    Args:
        service_file: The path to the systemd service file to install
        socket_file: The path to the systemd socket file to install
    """

    if service_file is None:
        return
    service_name = os.path.basename(service_file)

    logger.debug("...Installing user service '%s'.", service_name)

    # copy service file
    service_path = os.path.join(XINETD_SERVICE_PATH, service_name)
    shutil.copy2(service_file, service_path)


def generate_instance(problem_object,
                      problem_directory,
                      instance_number,
                      staging_directory,
                      deployment_directory=None):
    """
    Runs the setup functions of Problem in the correct order

    Args:
        problem_object: The contents of the problem.json
        problem_directory: The directory to the problem
        instance_number: The instance number to be generated
        staging_directory: The temporary directory to store files in
        deployment_directory: The directory that will be deployed to. Defaults to a deterministic, unique
                              directory generated for each problem,instance pair using the configuration options
                              PROBLEM_DIRECTORY_ROOT and OBFUSCATE_PROBLEM_DIRECTORIES

    Returns:
        A dict containing (problem, staging_directory, deployment_directory, files,
                           web_accessible_files, service_file, socket_file)
    """

    logger.debug("Generating instance %d of problem '%s'.", instance_number,
                 problem_object["unique_name"])
    logger.debug("...Using staging directory %s", staging_directory)

    username, new = create_instance_user(problem_object['name'],
                                         instance_number)
    if new:
        logger.debug("...Created problem user '%s'.", username)
    else:
        logger.debug("...Using existing problem user '%s'.", username)

    if deployment_directory is None:
        deployment_directory = generate_instance_deployment_directory(username)
    logger.debug("...Using deployment directory '%s'.", deployment_directory)

    seed = generate_seed(problem_object['name'], shared_config.deploy_secret,
                         str(instance_number))
    logger.debug("...Generated random seed '%s' for deployment.", seed)

    copy_path = join(staging_directory, PROBLEM_FILES_DIR)
    shutil.copytree(problem_directory, copy_path)

    pretemplated_directory = join(copy_path, "__pre_templated")

    if isdir(pretemplated_directory):
        shutil.rmtree(pretemplated_directory)

    # store cwd to restore later
    cwd = os.getcwd()
    os.chdir(copy_path)

    challenge = SourceFileLoader("challenge",
                                 join(copy_path, "challenge.py")).load_module()

    Problem = update_problem_class(challenge.Problem, problem_object, seed,
                                   username, deployment_directory)

    # run methods in proper order
    problem = Problem()

    # reseed and generate flag
    problem.flag = problem.generate_flag(Random(seed))
    problem.flag_sha1 = sha1(problem.flag.encode("utf-8")).hexdigest()
    logger.debug("...Instance %d flag is '%s'.", instance_number, problem.flag)

    logger.debug("...Running problem initialize.")
    problem.initialize()

    shutil.copytree(copy_path, pretemplated_directory)

    web_accessible_files = []

    def url_for(web_accessible_files,
                source_name,
                display=None,
                raw=False,
                pre_templated=False):
        if pre_templated:
            source_path = join(copy_path, "__pre_templated", source_name)
        else:
            source_path = join(copy_path, source_name)

        problem_hash = problem_object["name"] + shared_config.deploy_secret + str(
            instance_number)
        problem_hash = md5(problem_hash.encode("utf-8")).hexdigest()

        destination_path = join(STATIC_FILE_ROOT, problem_hash, source_name)

        link_template = "<a href='{}'>{}</a>"

        web_accessible_files.append((source_path,
                                     join(shared_config.web_root,
                                          destination_path)))
        uri_prefix = "//"
        uri = join(uri_prefix, local_config.hostname, destination_path)

        if not raw:
            return link_template.format(
                uri, source_name if display is None else display)

        return uri

    problem.url_for = functools.partial(url_for, web_accessible_files)

    logger.debug("...Templating the staging directory")
    template_staging_directory(copy_path, problem)

    if isinstance(problem, Compiled):
        problem.compiler_setup()
    if isinstance(problem, Remote):
        problem.remote_setup()
    if isinstance(problem, FlaskApp):
        problem.flask_setup()
    if isinstance(problem, PHPApp):
        problem.php_setup()
    if isinstance(problem, Service):
        problem.service_setup()

    logger.debug("...Running problem setup.")
    problem.setup()

    os.chdir(cwd)

    all_files = copy(problem.files)

    if isinstance(problem, Compiled):
        all_files.extend(problem.compiled_files)
    if isinstance(problem, Service):
        all_files.extend(problem.service_files)

    if not all([isinstance(f, File) for f in all_files]):
        logger.error("All files must be created using the File class!")
        raise FatalException

    for f in all_files:
        if not isinstance(f, Directory) and not os.path.isfile(
                join(copy_path, f.path)):
            logger.error("File '%s' does not exist on the file system!", f)

    service_file, socket_file = create_service_files(problem, instance_number,
                                                     staging_directory)
    logger.debug("...Created service files '%s','%s'.", service_file,
                 socket_file)


    # template the description
    # change newline for <br>, otherwise it won't render on the pico website
    problem.description = template_string(problem.description,
                                          **get_attributes(problem)).replace('\n','<br>')
    logger.debug("...Instance description: %s", problem.description)

    return {
        "problem": problem,
        "staging_directory": staging_directory,
        "deployment_directory": deployment_directory,
        "files": all_files,
        "web_accessible_files": web_accessible_files,
        "service_file": service_file,
        "socket_file": socket_file
    }


def deploy_problem(problem_directory,
                   instances=None,
                   test=False,
                   deployment_directory=None,
                   debug=False,
                   restart_xinetd=True):
    """
    Deploys the problem specified in problem_directory.

    Args:
        problem_directory: The directory storing the problem
        instances: The list of instances to deploy. Defaults to [0]
        test: Whether the instances are test instances. Defaults to False.
        deployment_directory: If not None, the challenge will be deployed here
                              instead of their home directory
        debug: Output debug info
        restart_xinetd: Whether to restart xinetd upon deployment of this set
                        of instances for a problem. Defaults True as used by
                        tests, but typically is used with False from
                        deploy_problems, which takes in multiple problems.

    """

    if instances is None:
        instances = [0]
    global current_problem, current_instance, port_map

    problem_object = get_problem(problem_directory)

    current_problem = problem_object["unique_name"]

    instance_list = []

    need_restart_xinetd = False

    logger.debug("Beginning to deploy problem '%s'.", problem_object["name"])

    problem_deb_location = os.path.join(
        DEB_ROOT, sanitize_name(problem_object['unique_name'])) + '.deb'
    try:
        subprocess.run('DEBIAN_FRONTEND=noninteractive apt-get -y install ' +
                       f'--reinstall {problem_deb_location}',
                       shell=True, check=True, stdout=subprocess.PIPE)
    except subprocess.CalledProcessError:
        logger.error("An error occurred while installing problem packages.")
        raise FatalException
    logger.debug("Reinstalled problem's deb package to fulfill dependencies")

    for instance_number in instances:
        current_instance = instance_number
        staging_directory = generate_staging_directory(
            problem_name=problem_object["name"],
            instance_number=instance_number)
        if test and deployment_directory is None:
            deployment_directory = join(staging_directory, "deployed")

        instance = generate_instance(
            problem_object,
            problem_directory,
            instance_number,
            staging_directory,
            deployment_directory=deployment_directory)
        instance_list.append((instance_number, instance))

    deployment_json_dir = join(DEPLOYED_ROOT,
                               "{}-{}".format(sanitize_name(problem_object["name"]),
                               get_pid_hash(problem_object, True)))
    if not os.path.isdir(deployment_json_dir):
        os.makedirs(deployment_json_dir)

    # ensure that the deployed files are not world-readable
    os.chmod(DEPLOYED_ROOT, 0o750)

    # all instances generated without issue. let's do something with them
    for instance_number, instance in instance_list:
        problem_path = join(instance["staging_directory"], PROBLEM_FILES_DIR)
        problem = instance["problem"]
        deployment_directory = instance["deployment_directory"]

        logger.debug("...Copying problem files %s to deployment directory %s.",
                     instance["files"], deployment_directory)
        deploy_files(problem_path, deployment_directory, instance["files"],
                     problem.user, problem.__class__)

        if test:
            logger.info("Test instance %d information:", instance_number)
            logger.info("...Description: %s", problem.description)
            logger.info("...Deployment Directory: %s", deployment_directory)

            logger.debug("Cleaning up test instance side-effects.")
            logger.debug("...Killing user processes.")
            # This doesn't look great.
            try:
                execute("killall -u {}".format(problem.user))
                sleep(0.1)
            except RunProcessError as e:
                pass

            logger.debug("...Removing test user '%s'.", problem.user)
            execute(["userdel", problem.user])

            deployment_json_dir = instance["staging_directory"]
        else:
            # copy files to the web root
            logger.debug("...Copying web accessible files: %s",
                         instance["web_accessible_files"])
            for source, destination in instance["web_accessible_files"]:
                if not os.path.isdir(os.path.dirname(destination)):
                    os.makedirs(os.path.dirname(destination))
                shutil.copy2(source, destination)

            if instance["service_file"] is not None:
                install_user_service(instance["service_file"],
                                     instance["socket_file"])
                # set to true, this will signal restart xinetd
                need_restart_xinetd = True

            # keep the staging directory if run with debug flag
            # this can still be cleaned up by running "shell_manager clean"
            if not debug:
                shutil.rmtree(instance["staging_directory"])

        deployment_info = {
            "user":
            problem.user,
            "deployment_directory":
            deployment_directory,
            "service":
            None if instance["service_file"] is None else
            os.path.basename(instance["service_file"]),
            "socket":
            None if instance["socket_file"] is None else os.path.basename(
                instance["socket_file"]),
            "server":
            problem.server,
            "description":
            problem.description,
            "flag":
            problem.flag,
            "flag_sha1":
            problem.flag_sha1,
            "instance_number":
            instance_number,
            "should_symlink":
            not isinstance(problem, Service) and len(instance["files"]) > 0,
            "files": [f.to_dict() for f in instance["files"]]
        }

        if isinstance(problem, Service):
            deployment_info["port"] = problem.port
            logger.debug("...Port %d has been allocated.", problem.port)

        port_map[(current_problem, instance_number)] = deployment_info.get(
            "port", None)

        instance_info_path = os.path.join(deployment_json_dir,
                                          "{}.json".format(instance_number))
        with open(instance_info_path, "w") as f:
            f.write(
                json.dumps(deployment_info, indent=4, separators=(", ", ": ")))

        logger.debug(
            "The instance deployment information can be found at '%s'.",
            instance_info_path)

    # restart xinetd
    if restart_xinetd and need_restart_xinetd:
        execute(["service", "xinetd", "restart"], timeout=60)

    logger.info("Problem instances %s were successfully deployed for '%s'.",
                instances, problem_object["unique_name"])
    return need_restart_xinetd


def deploy_problems(args):
    """ Main entrypoint for problem deployment """

    global shared_config, local_config, port_map
    shared_config = get_shared_config()
    local_config = get_local_config()

    need_restart_xinetd = False

    try:
        user = getpwnam(shared_config.default_user)
    except KeyError as e:
        logger.info("default_user '%s' does not exist. Creating the user now.",
                    shared_config.default_user)
        create_user(shared_config.default_user)

    problem_names = args.problem_names

    if len(problem_names) == 1 and problem_names[0] == 'all':
        # Shortcut to deploy n instances of all problems
        problem_names = [v['unique_name'] for k, v in get_all_problems().items()]

    # Attempt to load the port_map from file
    try:
        port_map_path = join(SHARED_ROOT, 'port_map.json')
        with open(port_map_path, 'r') as f:
            port_map = json.load(f)
            port_map = {literal_eval(k): v for k, v in port_map.items()}
    except FileNotFoundError:
        # If it does not exist, create it
        for path, problem in get_all_problems().items():
            for instance in get_all_problem_instances(path):
                port_map[(problem["unique_name"],
                          instance["instance_number"])] = instance.get("port", None)
        with open(port_map_path, 'w') as f:
            stringified_port_map = {repr(k): v for k, v in port_map.items()}
            json.dump(stringified_port_map, f)
    except IOError:
        logger.error(f"Error loading port map from {port_map_path}")
        raise

    acquire_lock()

    if args.instances:
        instance_list = args.instances
    else:
        instance_list = list(range(0, args.num_instances))

    try:
        for problem_name in problem_names:
            if not isdir(get_problem_root(problem_name, absolute=True)):
                logger.error(f"'{problem_name}' is not an installed problem")
                continue
            source_location = get_problem_root(problem_name, absolute=True)

            problem_object = get_problem(source_location)

            instances_to_deploy = copy(instance_list)
            is_static_flag = problem_object.get("static_flag", False)
            if is_static_flag is True:
                instances_to_deploy = [0]

            # Avoid redeploying already-deployed instances
            if not args.redeploy or is_static_flag:
                already_deployed = set()
                for instance in get_all_problem_instances(problem_name):
                    already_deployed.add(instance["instance_number"])
                instances_to_deploy = list(set(instances_to_deploy) - already_deployed)

            if instances_to_deploy:
                deploy_problem(
                    source_location,
                    instances=instances_to_deploy,
                    test=args.dry,
                    debug=args.debug,
                    restart_xinetd=False)
            else:
                logger.info("No additional instances to deploy for '%s'.",
                            problem_object["unique_name"])
    finally:
        # Restart xinetd unless specified. Service must be manually restarted
        if not args.no_restart:
            execute(["service", "xinetd", "restart"], timeout=60)

        # Write out updated port map
        with open(port_map_path, 'w') as f:
            stringified_port_map = {repr(k): v for k, v in port_map.items()}
            json.dump(stringified_port_map, f)

        release_lock()


def remove_instances(problem_name, instances_to_remove):
    """Remove all files and metadata for a given list of instances."""
    deployed_instances = get_all_problem_instances(problem_name)
    deployment_json_dir = join(DEPLOYED_ROOT, problem_name)

    for instance in deployed_instances:
        instance_number = instance["instance_number"]
        if instance["instance_number"] in instances_to_remove:
            logger.debug(
                f"Removing instance {instance_number} of {problem_name}")

            service = instance["service"]
            if service:
                logger.debug("...Removing xinetd service '%s'.", service)
                os.remove(join(XINETD_SERVICE_PATH, service))

            directory = instance["deployment_directory"]
            logger.debug("...Removing deployment directory '%s'.", directory)
            shutil.rmtree(directory)

            user = instance["user"]
            logger.debug("...Removing problem user '%s'.", user)
            execute(["userdel", user])

            deployment_json_path = join(deployment_json_dir,
                                        "{}.json".format(instance_number))
            logger.debug(
                "...Removing instance metadata '%s'.", deployment_json_path)
            os.remove(deployment_json_path)
    logger.info("Problem instances %s were successfully removed for '%s'.",
                instances_to_remove, problem_name)

def undeploy_problems(args):
    """
    Main entrypoint for problem undeployment

    Does not remove the installed packages (apt-get remove [sanitized name with hash]).
    Does not remove the problem from the web server (delete it from the mongo db).
    """

    problem_names = args.problem_names

    if len(problem_names) == 0:
        logger.error("No problem name(s) specified")
        raise FatalException

    if len(problem_names) == 1 and problem_names[0] == 'all':
        # Shortcut to undeploy n instances of all problems
        problem_names = [v['unique_name'] for k, v in get_all_problems().items()]

    acquire_lock()

    if args.instances:
        instance_list = args.instances
    else:
        instance_list = list(range(0, args.num_instances))

    try:
        for problem_name in problem_names:
            if not isdir(get_problem_root(problem_name, absolute=True)):
                logger.error(f"'{problem_name}' is not an installed problem")
                continue

            instances_to_remove = copy(instance_list)
            deployed_instances = set()
            for instance in get_all_problem_instances(problem_name):
                deployed_instances.add(instance["instance_number"])
            instances_to_remove = list(
                set(instances_to_remove).intersection(deployed_instances))

            if len(instances_to_remove) == 0:
                logger.warning(
                    f"No deployed instances found for {problem_name}")
                continue

            remove_instances(problem_name, instances_to_remove)
    finally:
        execute(["service", "xinetd", "restart"], timeout=60)
        release_lock()
