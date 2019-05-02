"""Routing functions for /api/problem."""
import json

from flask import Blueprint, request

import api.auth
import api.config
import api.problem
import api.problem_feedback
import api.user
from api.annotations import (block_after_competition, block_before_competition,
                             check_csrf, require_admin, require_login,
                             require_teacher)
from api.common import WebError, WebSuccess

blueprint = Blueprint("problem_api", __name__)


@blueprint.route('/submit', methods=['POST'])
@check_csrf
@require_login
@block_before_competition()
@block_after_competition()
def submit_key_hook():
    user_account = api.user.get_user()
    tid = user_account['tid']
    uid = user_account['uid']
    pid = request.form.get('pid', '')
    key = request.form.get('key', '')
    method = request.form.get('method', '')
    ip = request.remote_addr

    (correct, previously_solved_by_user,
     previously_solved_by_team) = api.problem.submit_key(
            tid, pid, key, method, uid, ip)

    if correct and not previously_solved_by_team:
        return WebSuccess("That is correct!"), 200
    elif not correct and not previously_solved_by_team:
        return WebError("That is incorrect!"), 200
    elif correct and previously_solved_by_user:
        return WebSuccess(
            'Flag correct: however, you have already solved ' +
            'this problem.'
        ), 200
    elif correct and previously_solved_by_team:
        return WebSuccess(
            'Flag correct: however, your team has already received points ' +
            'for this flag.'
        ), 200
    elif not correct and previously_solved_by_user:
        return WebError(
            'Flag incorrect: please note that you have ' +
            'already solved this problem.'
        ), 200
    elif not correct and previously_solved_by_team:
        return WebError(
            'Flag incorrect: please note that someone on your team has ' +
            'already solved this problem.'
        ), 200


@blueprint.route('/feedback', methods=['POST'])
@check_csrf
@require_login
@block_before_competition()
def problem_feedback_hook():
    feedback = json.loads(request.form.get("feedback", ""))
    pid = request.form.get("pid", None)

    if feedback is None or pid is None:
        return WebError("Please supply a pid and feedback."), 400

    if not api.config.get_settings()["enable_feedback"]:
        return WebError(
            "Problem feedback is not currently being accepted."), 403

    api.problem_feedback.add_problem_feedback(pid, api.auth.get_uid(),
                                              feedback)
    return WebSuccess("Your feedback has been accepted."), 201


@blueprint.route('/feedback/reviewed', methods=['GET'])
@require_login
@block_before_competition()
def problem_reviews_hook():
    uid = api.user.get_user()['uid']
    return WebSuccess(
        data=api.problem_feedback.get_problem_feedback(uid=uid)), 200


@blueprint.route("/hint", methods=['GET'])
@require_login
@block_before_competition()
def request_problem_hint_hook():
    source = request.args.get("source")
    pid = request.args.get("pid")

    if pid is None:
        return WebError("Please supply a pid."), 400
    if source is None:
        return WebError("You have to supply the source of the hint."), 400

    tid = api.user.get_team()["tid"]
    if pid not in api.problem.get_unlocked_pids(tid):
        return WebError("Your team hasn't unlocked this problem yet!"), 403

    return WebSuccess("Hint noted."), 200


@blueprint.route('/clear_submissions', methods=['GET'])
@require_login
@require_admin
def clear_all_submissions_hook():
    api.problem.clear_all_submissions()
    return WebSuccess("All submissions reset."), 200
