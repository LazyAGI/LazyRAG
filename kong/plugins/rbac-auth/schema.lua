return {
  name = "rbac-auth",
  fields = {
    { config = {
        type = "record",
        fields = {
          { auth_service_url = {
              type = "string",
              default = "http://auth-service:8000",
              description = "Base URL of auth-service (e.g. http://auth-service:8000)",
            },
          },
        },
      },
    },
  },
}
