"""Merchant service - producer onboarding API."""
import logging

from shared.http import ApiError, error, json_body, path_param, require_group, resp, sub

from . import domain, repo

log = logging.getLogger()
log.setLevel(logging.INFO)


def lambda_handler(event, _context):
    try:
        return _route(event)
    except ApiError as exc:
        return error(exc.status, exc.message)
    except Exception:  # noqa: BLE001 - last-resort guard, details go to logs only
        log.exception("unhandled error")
        return error(500, "internal error")


def _route(event):
    key = event.get("routeKey", "")

    if key == "POST /v1/stalls":
        require_group(event, "stall-owner")
        stall = domain.new_stall(sub(event), json_body(event))
        repo.put_stall(stall)
        return resp(201, stall)

    if key == "GET /v1/me/stalls":
        return resp(200, {"stalls": repo.list_by_owner(sub(event))})

    if key == "PATCH /v1/stalls/{stallId}":
        require_group(event, "stall-owner")
        stall = repo.get_stall(path_param(event, "stallId"))
        if stall["ownerSub"] != sub(event):
            raise ApiError(403, "not the owner of this stall")
        status = domain.validate_status(json_body(event).get("status", ""))
        return resp(200, repo.set_status(stall["stallId"], status))

    raise ApiError(404, "route not found")
