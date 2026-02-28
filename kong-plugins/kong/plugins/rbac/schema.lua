-- RBAC plugin config schema
-- path_roles: path -> allowed roles; consumer_roles: consumer -> role mapping

return {
  name = "rbac",
  fields = {
    {
      config = {
        type = "record",
        fields = {
          {
            path_roles = {
              type = "array",
              required = true,
              default = {},
              elements = {
                type = "record",
                fields = {
                  {
                    path = {
                      type = "string",
                      required = true,
                    },
                  },
                  {
                    roles = {
                      type = "array",
                      required = true,
                      elements = {
                        type = "string",
                      },
                    },
                  },
                },
              },
            },
          },
          {
            consumer_roles = {
              type = "array",
              required = true,
              default = {},
              elements = {
                type = "record",
                fields = {
                  {
                    consumer = {
                      type = "string",
                      required = true,
                    },
                  },
                  {
                    role = {
                      type = "string",
                      required = true,
                    },
                  },
                },
              },
            },
          },
          {
            default_role = {
              type = "string",
              required = false,
              default = "user",
            },
          },
        },
      },
    },
  },
}
