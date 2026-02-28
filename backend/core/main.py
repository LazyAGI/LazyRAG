from fastapi import FastAPI

from rbac import PermissionProtectedRoute, permission_required

app = FastAPI(title="Core Service")
app.router.route_class = PermissionProtectedRoute


@app.get("/hello")
def hello():
    return {"message": "Hello from Backend"}


@app.get("/admin")
def admin():
    return {"message": "Admin only area"}


@app.get("/api/hello")
@permission_required("user.read")
def api_hello():
    return {"message": "Hello from Backend"}


@app.get("/api/admin")
@permission_required("document.write")
def api_admin():
    return {"message": "Admin only area"}
