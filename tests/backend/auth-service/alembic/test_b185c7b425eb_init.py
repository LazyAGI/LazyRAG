import importlib.util
from pathlib import Path


REVISION_FILE = (
    Path(__file__).resolve().parents[4]
    / 'backend'
    / 'auth-service'
    / 'alembic'
    / 'versions'
    / 'b185c7b425eb_init.py'
)


def _load_revision_module():
    spec = importlib.util.spec_from_file_location('_auth_alembic_revision_b185c7b425eb', REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeOp:
    def __init__(self):
        self.calls = []

    def f(self, name):
        return f'op_f:{name}'

    def create_table(self, name, *elements):
        self.calls.append(('create_table', name, elements))

    def create_index(self, name, table_name, columns, unique=False):
        self.calls.append(('create_index', name, table_name, tuple(columns), unique))

    def drop_index(self, name, table_name):
        self.calls.append(('drop_index', name, table_name))

    def drop_table(self, name):
        self.calls.append(('drop_table', name))


def _column_names(elements):
    return [element.name for element in elements if hasattr(element, 'name')]


def _constraint_names(elements):
    return [getattr(element, 'name', None) for element in elements if element.__class__.__name__.endswith('Constraint')]


def test_revision_identifiers_are_stable():
    module = _load_revision_module()

    assert module.revision == 'b185c7b425eb'
    assert module.down_revision is None
    assert module.branch_labels is None
    assert module.depends_on is None


def test_upgrade_creates_auth_tables_indexes_and_constraints():
    module = _load_revision_module()
    fake_op = _FakeOp()
    module.op = fake_op

    module.upgrade()

    create_table_calls = [call for call in fake_op.calls if call[0] == 'create_table']
    create_index_calls = [call for call in fake_op.calls if call[0] == 'create_index']

    assert [call[1] for call in create_table_calls] == [
        'permission_groups',
        'roles',
        'role_permissions',
        'users',
        'groups',
        'group_permissions',
        'user_groups',
    ]
    assert len(create_index_calls) == 18
    assert ('create_index', 'op_f:ix_users_username', 'users', ('username',), True) in create_index_calls
    assert ('create_index', 'op_f:ix_permission_groups_code', 'permission_groups', ('code',), True) in create_index_calls

    tables = {call[1]: call[2] for call in create_table_calls}
    assert _column_names(tables['users']) == [
        'id',
        'username',
        'display_name',
        'password_hash',
        'role_id',
        'tenant_id',
        'email',
        'phone',
        'remark',
        'creator',
        'created_at',
        'updated_at',
        'last_login_time',
        'updated_pwd_time',
        'disabled',
        'source',
    ]
    assert 'uq_role_permission' in _constraint_names(tables['role_permissions'])
    assert 'uq_tenant_group_name' in _constraint_names(tables['groups'])
    assert 'uq_group_permission' in _constraint_names(tables['group_permissions'])
    assert 'uq_tenant_user_group' in _constraint_names(tables['user_groups'])


def test_downgrade_drops_indexes_and_tables_in_dependency_order():
    module = _load_revision_module()
    fake_op = _FakeOp()
    module.op = fake_op

    module.downgrade()

    drop_table_calls = [call for call in fake_op.calls if call[0] == 'drop_table']
    drop_index_calls = [call for call in fake_op.calls if call[0] == 'drop_index']

    assert [call[1] for call in drop_table_calls] == [
        'user_groups',
        'group_permissions',
        'groups',
        'users',
        'role_permissions',
        'roles',
        'permission_groups',
    ]
    assert len(drop_index_calls) == 18
    assert fake_op.calls[0] == ('drop_index', 'op_f:ix_user_groups_user_id', 'user_groups')
    assert fake_op.calls[-1] == ('drop_table', 'permission_groups')
