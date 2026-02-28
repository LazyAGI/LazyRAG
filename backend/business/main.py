from fastapi import FastAPI

from rbac import RoleProtectedRoute, roles_required

app = FastAPI(title="Business Service")
app.router.route_class = RoleProtectedRoute


@app.get("/hello")
def hello():
    return {"message": "Hello from Backend"}


@app.get("/admin")
def admin():
    return {"message": "Admin only area"}


@app.get("/api/hello")
@roles_required("user", "admin")
def api_hello():
    return {"message": "Hello from Backend"}


@app.get("/api/admin")
@roles_required("admin")
def api_admin():
    return {"message": "Admin only area"}
