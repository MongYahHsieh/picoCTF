"""Module for calculating gameplay statistics."""

import datetime
import math
import pymongo

import api
from api.cache import (decode_scoreboard_item, get_score_cache,
                       get_scoreboard_cache, get_scoreboard_key, memoize,
                       search_scoreboard_cache)
from api import PicoException


SCOREBOARD_PAGE_LEN = 50


def _get_problem_names(problems):
    """Extract the names from a list of problems."""
    return [problem['name'] for problem in problems]


# @memoize
def get_score(tid=None, uid=None, time_weighted=True):
    """
    Get the score for a user or team. Uses memoization from zset keyed on
    uid/tid. Currently the sorted aspect of this set doesn't exactly serve
    any function...

    Args:
        tid: The team id
        uid: The user id
        time_weighted: return decimal weight of time of last solved problem
    Returns:
        float score: The users's or team's int score, plus decimal value of
        weighting based last submission time. Cast as int for all
        score display output, never round
    """
    if uid is None:
        cache_key = tid
        solved_args = {"tid": tid}
    elif tid is None:
        cache_key = uid
        solved_args = {"uid": uid}
    else:
        cache_key = tid + uid
        solved_args = {"uid": uid, "tid": tid}

    score_cache = get_score_cache()
    score = score_cache.score(cache_key)

    # Not cached
    if score is None:
        db = api.db.get_conn()
        solved_problems = api.problem.get_solved_problems(**solved_args)
        score = sum([
            problem['score']
            for problem in solved_problems
        ])
        time_weight = 0
        if score > 0:
            solved_args.update({'correct': True})
            last_submitted = datetime.datetime.now()
            # Search by individual team members, which may include
            # submissions made before joining current team
            if tid is not None:
                members = api.team.get_team_members(tid=tid,
                                                    show_disabled=False)
                solved_args = {
                    "uid": {
                        "$in": list(map(lambda x: x["uid"], members))
                    }
                }
            query = db.submissions.find(solved_args).limit(1).sort(
                [('$natural', pymongo.DESCENDING)])
            if query.count() > 0:
                last_submitted = query[0]['timestamp']
            # Weight returns a float based on last submission time.
            # Math is safe for next 2 centuries
            time_weight = 1 - (int(last_submitted.strftime("%s")) * 1e-10)
        score += time_weight
        score_cache.add({cache_key: score})
    if time_weighted:
        return score
    else:
        return int(score)


def get_team_review_count(tid=None, uid=None):
    """
    Get the count of reviewed problems for a user or team.

    Args:
        tid: team to get count of
        uid: user to get count of (overrides tid)

    Returns: review count
    """
    if uid is not None:
        return len(api.problem_feedback.get_reviewed_pids(uid=uid))
    elif tid is not None:
        count = 0
        for member in api.team.get_team_members(tid=tid):
            count += len(
                api.problem_feedback.get_reviewed_pids(uid=member['uid']))
        return count


# Stored by the cache_stats daemon.
# @memoize
def get_group_scores(gid=None, name=None):
    """
    Get the group scores.

    Args:
        gid: The group id
        name: The group name
    Returns:
        A dictionary containing name, tid, and score
    """
    key_args = {'gid': gid}
    scoreboard_cache = get_scoreboard_cache(**key_args)
    scoreboard_cache.clear()

    member_teams = [
        api.team.get_team(tid=tid)
        for tid in api.group.get_group(gid=gid)['members']
    ]

    result = {}
    for team in member_teams:
        if team["size"] > 0:
            score = get_score(tid=team['tid'])
            key = get_scoreboard_key(team)
            result[key] = score
    if result:
        scoreboard_cache.add(result)

    return scoreboard_cache


def get_group_average_score(gid=None, name=None):
    """
    Get the average score of teams in a group.

    Args:
        gid: The group id
        name: The group name
    Returns:
        The total score of the group
    """
    group_scoreboard = get_group_scores(gid=gid, name=name)
    group_scores = group_scoreboard.as_items()
    total_score = sum([int(item[1]) for item in group_scores])
    return int(total_score / len(group_scores)) if len(group_scores) > 0 else 0


# Stored by the cache_stats daemon
# @memoize
def get_all_team_scores(country=None, include_ineligible=False):
    """
    Get the score for every team in the database.

    Args:
        country: optional restriction by country
        include_ineligible: include ineligible teams

    Returns:
        A list of dictionaries with name and score

    """
    key_args = {'country': country, 'include_ineligible': include_ineligible}
    teams = api.team.get_all_teams(**key_args)
    scoreboard_cache = get_scoreboard_cache(**key_args)
    scoreboard_cache.clear()

    result = {}
    all_groups = api.group.get_all_groups()
    for team in teams:
        # Get the full version of the group.
        groups = [
            group for group in all_groups if team["tid"] in group["members"] or
            team["tid"] in group["teachers"] or team["tid"] == group["owner"]
        ]

        # Determine if the user is exclusively a member of hidden groups.
        # If they are, they won't be processed.
        if (len(groups) == 0 or
                any([not (group["settings"]["hidden"]) for group in groups])):
            score = get_score(tid=team['tid'])
            if score > 0:
                key = get_scoreboard_key(team=team)
                result[key] = score
    if result:
        scoreboard_cache.add(result)
    return scoreboard_cache


def get_all_user_scores():
    """
    Get the score for every user in the database.

    Returns:
        A list of dictionaries with name and score

    """
    users = api.user.get_all_users()

    result = []
    for user in users:
        result.append({
            "name": user['username'],
            "score": get_score(uid=user['uid'], time_weighted=False)
        })

    return sorted(result, key=lambda item: item['score'], reverse=True)


@memoize(timeout=120)
def get_problems_by_category():
    """
    Get the list of all problems divided into categories.

    Returns:
        A dictionary of category:[problem list]

    """
    result = {
        cat: _get_problem_names(api.problem.get_all_problems(category=cat))
        for cat in api.problem.get_all_categories()
    }

    return result


def get_team_member_stats(tid):
    """
    Get the solved problems for each member of a given team.

    Args:
        tid: the team id

    Returns:
        A dict of username:[problem list]

    """
    members = api.team.get_team_members(tid=tid)

    return {
        member['username']: _get_problem_names(
            api.problem.get_solved_problems(uid=member['uid']))
        for member in members
    }


def get_problem_submission_stats(pid=None):
    """
    Retrieve the number of valid and invalid submissions for a given problem.

    Args:
        pid: the pid of the problem
        name: the name of the problem
    Returns:
        Dict of {valid: #, invalid: #}
    """
    return {
        "valid":
        len(api.submissions.get_submissions(pid, correctness=True)),
        "invalid":
        len(
            api.submissions.get_submissions(pid, correctness=False))
    }


@memoize
def get_score_progression(tid=None, uid=None, category=None):
    """
    Find the score and time after each correct submission of a team or user.

    NOTE: this is slower than get_score.
          Do not use this for getting current score.

    Args:
        tid: the tid of the user
        uid: the uid of the user
        category: category filter
    Returns:
        A list of dictionaries containing score and time
    """
    solved = api.problem.get_solved_problems(
        tid=tid, uid=uid, category=category)

    result = []
    score = 0

    problems_counted = set()

    for problem in sorted(solved, key=lambda prob: prob["solve_time"]):
        if problem['pid'] not in problems_counted:
            score += problem["score"]
            problems_counted.add(problem['pid'])
        result.append({
            "score": score,
            "time": int(problem["solve_time"].timestamp())
        })

    return result


# Stored by the cache_stats daemon
@memoize
def get_problem_solves(pid):
    """
    Return the number of solves for a particular problem.

    Args:
        pid: pid of the problem
    """
    db = api.db.get_conn()

    return db.submissions.count({
        'pid': pid,
        'correct': True
    })


# Stored by the cache_stats daemon
@memoize
def get_top_teams_score_progressions(
        limit=5, include_ineligible=False, gid=None):
    """
    Get the score progressions for the top teams.

    Args:
        limit: Number of teams to include
        gid: If specified, compute the progressions for the top teams
             from this group only. Overrides include_ineligible.
        include_ineligible: if specified, include ineligible teams in result

    Returns:
        The top teams and their score progressions.
        A dict of {name: name, score_progression: score_progression}

    """
    def output_item(item):
        data = decode_scoreboard_item(item)
        return {
            'name': data['name'],
            'affiliation': data['affiliation'],
            'score_progression': get_score_progression(tid=data['tid'])
        }

    if gid is None:
        scoreboard_cache = get_all_team_scores(
            include_ineligible=include_ineligible)
    else:
        scoreboard_cache = get_group_scores(gid=gid)

    team_items = scoreboard_cache.range(0, limit - 1, with_scores=True,
                                        desc=True)
    return [output_item(team_item) for team_item in team_items]


@memoize()
def check_invalid_instance_submissions(gid=None):
    """Get submissions of keys for the wrong problem instance."""
    db = api.db.get_conn()
    shared_key_submissions = []

    group = None
    if gid is not None:
        group = api.group.get_group(gid=gid)

    for problem in api.problem.get_all_problems(show_disabled=True):
        valid_keys = [instance['flag'] for instance in problem['instances']]
        incorrect_submissions = db.submissions.find({
            'pid': problem['pid'],
            'correct': False
        }, {"_id": 0})
        for submission in incorrect_submissions:
            if submission['key'] in valid_keys:
                # make sure that the key is still invalid
                if not api.submissions.grade_problem(
                        submission['pid'], submission['key'],
                        tid=submission['tid']):
                    if group is None or submission['tid'] in group['members']:
                        submission['username'] = api.user.get_user(
                            uid=submission['uid'])['username']
                        submission["problem_name"] = problem["name"]
                        shared_key_submissions.append(submission)

    return shared_key_submissions


# Stored by the cache_stats daemon.
@memoize
def get_registration_count():
    """Get the user, team, and group counts."""
    db = api.db.get_conn()
    users = db.users.count()
    stats = {
        "users": users,
        "teams": db.teams.count() - users,
        "groups": db.groups.count()
    }
    usernames = set(db.users.find({}).distinct("username"))
    team_names = set(db.teams.find({}).distinct("team_name"))

    real_team_names = team_names - usernames
    real_team_ids = list(
        db.teams.find({
            "team_name": {
                "$in": list(real_team_names)
            }
        }).distinct("tid"))

    teamed_users = db.users.count({"tid": {"$in": real_team_ids}})
    stats["teamed_users"] = teamed_users

    return stats


def get_initial_scoreboard():
    """
    Retrieve the initial scoreboard (first pages of global and student views).

    If a user is logged in, the initial pages will instead be those on which
    that user appears, and their group scoreboards will also be returned.

    Returns: dict of scoreboard information
    """
    user = None
    team = None
    pagelen = SCOREBOARD_PAGE_LEN

    if api.user.is_logged_in():
        user = api.user.get_user()
        team = api.team.get_team(tid=user['tid'])

    result = {'tid': 0, 'groups': []}
    # Include all arguments
    global_board = get_scoreboard_cache(country=None, include_ineligible=True)
    result['global'] = {
        'name': 'global',
        'pages': math.ceil(len(global_board) / pagelen),
        'start_page': 1,
        'scoreboard': [],
    }
    if user is None:
        raw_board = global_board.range(0, pagelen - 1, with_scores=True,
                                       desc=True)
        result['global']['scoreboard'] = [decode_scoreboard_item(item) for
                                          item in raw_board]
    else:
        result['tid'] = team['tid']

        # Display global board at particular page user is ranked at
        global_pos = global_board.rank(get_scoreboard_key(team),
                                       reverse=True) or 0
        start_slice = math.floor(global_pos / pagelen) * pagelen
        raw_board = global_board.range(start_slice, start_slice + pagelen - 1,
                                       with_scores=True, desc=True)
        result['global']['scoreboard'] = [decode_scoreboard_item(item) for
                                          item in raw_board]
        result['global']['start_page'] = math.ceil((global_pos + 1) / pagelen)

        # Eligible student board, starting at first page
        # result['country'] = user["country"]
        student_board = get_scoreboard_cache(country=None,
                                             include_ineligible=False)
        student_pos = student_board.rank(get_scoreboard_key(team),
                                         reverse=True) or 0
        start_slice = math.floor(student_pos / pagelen) * pagelen
        raw_student_board = student_board.range(start_slice,
                                                start_slice + pagelen - 1,
                                                with_scores=True,
                                                desc=True)
        result['student'] = {
            'name': 'student',
            'pages': math.ceil(len(student_board) / pagelen),
            'scoreboard': [decode_scoreboard_item(item) for
                           item in raw_student_board],
            'start_page': math.ceil((student_pos + 1) / pagelen),
        }

        # Each classroom/group
        for group in api.team.get_groups(user['tid']):
            group_board = get_scoreboard_cache(gid=group['gid'])
            group_pos = group_board.rank(get_scoreboard_key(team),
                                         reverse=True) or 0
            start_slice = math.floor(group_pos / pagelen) * pagelen
            raw_group_board = group_board.range(start_slice,
                                                start_slice + pagelen - 1,
                                                with_scores=True,
                                                desc=True)
            result['groups'].append({
                'gid':
                group['gid'],
                'name':
                group['name'],
                'scoreboard':
                [decode_scoreboard_item(item) for item in raw_group_board],
                'pages':
                math.ceil(len(group_board) / pagelen),
                'start_page':
                math.ceil((group_pos + 1) / pagelen),
            })
    return result


def get_scoreboard_page(board, page_number, gid=None):
    """
    Retrieve a specific scoreboard page.

    Must be logged in to retrieve a page from the 'groups' board.

    Args:
        board: scoreboard to retrieve a page from (global, student, groups)
        page_number: page number to retrieve

    Raises:
        PicoException: if the 'groups' board is selected but no user is
                       logged in

    """
    start = SCOREBOARD_PAGE_LEN * (page_number - 1)
    end = start + SCOREBOARD_PAGE_LEN - 1
    scoreboard = []
    if board == "groups":
        user = api.user.get_user()
        group = api.group.get_group(gid=gid)
        if not (user["tid"] in group["members"] or
                user["tid"] in group["teachers"] or
                user["tid"] == group["owner"]):
            raise PicoException(
                    "You are not a member of this class",
                    status_code=401)
        group_board = get_scoreboard_cache(gid=gid)
        raw_board = group_board.range(start, end, with_scores=True,
                                      reverse=True)
        scoreboard = [decode_scoreboard_item(item) for item in raw_board]
    elif board == "global":
        global_board = get_scoreboard_cache(country=None,
                                            include_ineligible=True)
        raw_board = global_board.range(start, end, with_scores=True,
                                       reverse=True)
        scoreboard = [decode_scoreboard_item(item) for item in raw_board]
    elif board == "student":
        student_board = get_scoreboard_cache(country=None,
                                             include_ineligible=False)
        raw_board = student_board.range(start, end, with_scores=True,
                                        reverse=True)
        scoreboard = [decode_scoreboard_item(item) for item in raw_board]
    return {
        'name': board,
        'pages': math.ceil(len(scoreboard) / SCOREBOARD_PAGE_LEN),
        'start_page': 1,
        'scoreboard': scoreboard
    }


def get_demographic_data():
    """Get demographic information used in analytics"""
    users = api.user.get_all_users()

    result = []
    for user in users:
        result.append({
            "usertype": user['usertype'],
            "country": user['country'],
            "gender": user['demo'].get('gender',''),
            "zipcode": user['demo'].get('zipcode',''),
            "grade": user['demo'].get('grade',''),
            "score": get_score(uid=user['uid'], time_weighted=False)
        })

    return result


def search_scoreboard(board, pattern, page=1):
    if board == "student":
        key_args = {'country': None, 'include_ineligible': False}
    else:  # default to global
        key_args = {'country': None, 'include_ineligible': True}
    scoreboard = get_scoreboard_cache(**key_args)
    results = search_scoreboard_cache(scoreboard, pattern)
    start = SCOREBOARD_PAGE_LEN * (page - 1)
    end = start + SCOREBOARD_PAGE_LEN
    boardlist = results[start:end]
    for item in boardlist:
        item['rank'] = scoreboard.rank(item['key'], reverse=True) + 1
        item.pop('key')
    return {
        'name': board,
        'pages': math.ceil(len(results) / SCOREBOARD_PAGE_LEN),
        'start_page': page,
        'scoreboard': boardlist
    }
