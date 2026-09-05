"""Catalog service - public browsing and owner menu management."""
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
    except Exception:  # noqa: BLE001
        log.exception("unhandled error")
        return error(500, "internal error")


def _route(event):
    key = event.get("routeKey", "")

    if key == "GET /v1/centres/{centreId}/stalls":
        return resp(200, {"stalls": repo.list_stalls_by_centre(path_param(event, "centreId"))})

    if key == "GET /v1/stalls/{stallId}":
        return resp(200, repo.get_stall(path_param(event, "stallId")))

    if key == "GET /v1/stalls/{stallId}/menu":
        return resp(200, {"items": repo.get_menu(path_param(event, "stallId"))})

    if key == "PUT /v1/stalls/{stallId}/menu/{itemId}":
        require_group(event, "stall-owner")
        stall = repo.get_stall(path_param(event, "stallId"))
        if stall["ownerSub"] != sub(event):
            raise ApiError(403, "not the owner of this stall")
        item = domain.validate_item(path_param(event, "itemId"), json_body(event))
        return resp(200, repo.put_item(stall["stallId"], item))

    raise ApiError(404, "route not found")
