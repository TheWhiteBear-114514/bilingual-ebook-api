"""业务响应码（与 docs/error-codes.md 对应）。"""


class ResponseCode:
    OK = 0
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    TOO_LARGE = 413
    UNPROCESSABLE = 422

    ENGINE_NOT_READY = 3001
    POINTS_NOT_ENOUGH = 3002
    PDF_NOT_SUPPORTED = 4001
    INTERNAL = 5001
