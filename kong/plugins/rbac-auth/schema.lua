local typedefs = require 'kong.db.schema.typedefs'

return {
  name = 'rbac-auth',
  fields = {
    { consumer = typedefs.no_consumer },
    { protocols = typedefs.protocols_http },
    {
      config = {
        type = 'record',
        fields = {
          {
            auth_service_url = {
              type = 'string',
              default = 'http://auth-service:8000',
            },
          },
          {
            timeout_ms = {
              type = 'integer',
              default = 5000,
            },
          },
        },
      },
    },
  },
}
