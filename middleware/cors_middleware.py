async def cors_middleware(request, call_next):
    response = await call_next(request)

    # Allow all origins for demo purposes. In production, specify allowed origins.
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"

    return response