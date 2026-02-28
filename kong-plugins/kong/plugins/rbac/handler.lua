-- RBAC plugin: authorize by request path and consumer role
-- Must run after key-auth (or similar) so authenticated consumer is available

local RBACHandler = {
  VERSION  = "1.0.0",
  PRIORITY = 900,  -- run after key-auth (1000)
}

local kong = kong

-- Find required roles for current path from path_roles config
local function get_required_roles_for_path(path, path_roles)
  for _, entry in ipairs(path_roles) do
    local pattern = entry.path
    if pattern == path or (pattern:sub(-1) == "/" and path:sub(1, #pattern) == pattern) then
      return entry.roles
    end
    -- Simple prefix match, e.g. /api/admin matches /api/admin/xxx
    if path:sub(1, #pattern) == pattern and (path:len() == #pattern or path:sub(#pattern + 1, #pattern + 1) == "/") then
      return entry.roles
    end
  end
  return nil  -- path not in config: no role restriction
end

-- Get consumer role from consumer_roles config
local function get_consumer_role(username, consumer_roles, default_role)
  for _, entry in ipairs(consumer_roles) do
    if entry.consumer == username then
      return entry.role
    end
  end
  return default_role
end

-- Check if role is in the allowed list
local function role_allowed(role, allowed_roles)
  if not allowed_roles then
    return true
  end
  for _, r in ipairs(allowed_roles) do
    if r == role then
      return true
    end
  end
  return false
end

function RBACHandler:access(conf)
  local consumer = kong.client.get_consumer()
  if not consumer then
    return kong.response.exit(403, {
      message = "Forbidden: authentication required",
    }, {
      ["Content-Type"] = "application/json",
    })
  end

  local username = consumer.username
  if not username then
    return kong.response.exit(403, {
      message = "Forbidden: consumer has no username",
    }, {
      ["Content-Type"] = "application/json",
    })
  end

  local path = kong.request.get_path()
  local path_roles = conf.path_roles or {}
  local consumer_roles = conf.consumer_roles or {}
  local default_role = conf.default_role or "user"

  local required_roles = get_required_roles_for_path(path, path_roles)
  if not required_roles then
    -- Path has no role requirement, allow
    return
  end

  local consumer_role = get_consumer_role(username, consumer_roles, default_role)
  if not role_allowed(consumer_role, required_roles) then
    return kong.response.exit(403, {
      message = "Forbidden: insufficient role",
      path = path,
      required_roles = required_roles,
      your_role = consumer_role,
    }, {
      ["Content-Type"] = "application/json",
    })
  end
end

return RBACHandler
