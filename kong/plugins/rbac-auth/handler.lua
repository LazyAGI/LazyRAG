local http  = require("resty.http")
local cjson = require("cjson.safe")

local RbacAuthHandler = {
  PRIORITY = 900,
  VERSION = "0.1.0",
}

function RbacAuthHandler:access(conf)
  local method = kong.request.get_method()
  local path = kong.request.get_path()
  local auth = kong.request.get_header("Authorization") or ""

  local url = (conf.auth_service_url:gsub("/+$", "")) .. "/api/auth/authorize"
  local body = cjson.encode({ method = method, path = path })

  local httpc = http.new()
  httpc:set_timeout(5000)
  local res, err = httpc:request_uri(url, {
    method = "POST",
    body = body,
    headers = {
      ["Content-Type"] = "application/json",
      ["Authorization"] = auth,
    },
  })

  if err then
    kong.log.err("rbac-auth: auth-service request failed: ", err)
    return kong.response.exit(503, { message = "Authorization service unavailable" },
      { ["Content-Type"] = "application/json" })
  end

  if res.status == 401 then
    return kong.response.exit(401, { detail = "Unauthorized" },
      { ["Content-Type"] = "application/json" })
  end

  if res.status == 403 then
    return kong.response.exit(403, { detail = "Forbidden" },
      { ["Content-Type"] = "application/json" })
  end

  if res.status ~= 200 then
    kong.log.err("rbac-auth: auth-service returned ", res.status)
    return kong.response.exit(502, { message = "Authorization check failed" },
      { ["Content-Type"] = "application/json" })
  end

  -- 200: allowed; continue to upstream
end

return RbacAuthHandler
