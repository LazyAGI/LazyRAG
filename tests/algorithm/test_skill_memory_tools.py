from chat.tools import memory as memory_mod
from chat.tools import skill_manager as skill_manager_mod


def test_memory_submits_core_api_suggestion_paths(monkeypatch):
    calls = []

    def fake_post_core_api(path, payload):
        calls.append((path, payload))
        return {'persisted': 'core_api', 'url': f'http://core{path}'}

    monkeypatch.setattr(
        memory_mod,
        '_agentic_config',
        lambda: {'session_id': 'sid-1', 'core_api_url': 'http://10.119.24.129:9090'},
    )
    monkeypatch.setattr(memory_mod, '_post_core_api', fake_post_core_api)

    suggestion = {'title': 'Keep preference', 'content': 'Remember the preference.'}

    memory_result = memory_mod.memory('memory', [suggestion])
    user_result = memory_mod.memory('user', [suggestion])

    assert memory_result['success'] is True
    assert user_result['success'] is True
    assert calls == [
        ('/memory/suggestion', {'session_id': 'sid-1', 'suggestions': [suggestion]}),
        ('/user_preference/suggestion', {'session_id': 'sid-1', 'suggestions': [suggestion]}),
    ]


def test_memory_requires_session_id(monkeypatch):
    monkeypatch.setattr(memory_mod, '_agentic_config', lambda: {})
    monkeypatch.setattr(memory_mod, '_session_id', lambda _config: '')

    result = memory_mod.memory(
        'memory',
        [{'title': 'Keep preference', 'content': 'Remember the preference.'}],
    )

    assert result == {
        'success': False,
        'reason': "'session_id' is required in agentic_config.",
    }


def test_skill_manage_create_modify_remove_use_core_api_paths(monkeypatch):
    calls = []

    def fake_post_core_api(path, payload):
        calls.append((path, payload))
        return {'persisted': 'core_api', 'url': f'http://core{path}'}

    monkeypatch.setattr(
        skill_manager_mod,
        '_agentic_config',
        lambda: {'session_id': 'sid-1', 'skill_fs_local_base_dir': '/tmp/skills'},
    )
    monkeypatch.setattr(skill_manager_mod, '_post_core_api', fake_post_core_api)
    monkeypatch.setattr(
        skill_manager_mod,
        'list_all_skills_with_category',
        lambda _base_dir: {'existing': 'writing'},
    )

    content = (
        '---\n'
        'name: new_skill\n'
        'description: A test skill.\n'
        '---\n'
        'Use this skill for tests.\n'
    )
    suggestion = {'title': 'Update instructions', 'content': 'Tighten the wording.'}

    create_result = skill_manager_mod.skill_manage(
        'new_skill',
        'create',
        category='drafts',
        content=content,
    )
    modify_result = skill_manager_mod.skill_manage(
        'existing',
        'modify',
        suggestions=[suggestion],
    )
    remove_result = skill_manager_mod.skill_manage('existing', 'remove')

    assert create_result['success'] is True
    assert modify_result['success'] is True
    assert remove_result['success'] is True
    assert calls == [
        (
            '/skill/create',
            {'session_id': 'sid-1', 'skill_name': 'new_skill', 'content': content},
        ),
        (
            '/skill/suggestion',
            {'session_id': 'sid-1', 'skill_name': 'existing', 'suggestions': [suggestion]},
        ),
        ('/skill/remove', {'session_id': 'sid-1', 'skill_name': 'existing'}),
    ]


def test_skill_manage_rejects_missing_skill_without_post(monkeypatch):
    calls = []

    monkeypatch.setattr(
        skill_manager_mod,
        '_agentic_config',
        lambda: {'session_id': 'sid-1', 'skill_fs_local_base_dir': '/tmp/skills'},
    )
    monkeypatch.setattr(skill_manager_mod, '_post_core_api', lambda path, payload: calls.append((path, payload)))
    monkeypatch.setattr(skill_manager_mod, 'list_all_skills_with_category', lambda _base_dir: {})

    result = skill_manager_mod.skill_manage(
        'missing',
        'modify',
        suggestions=[{'title': 'Update instructions', 'content': 'Tighten the wording.'}],
    )

    assert result == {
        'success': False,
        'reason': "Skill 'missing' does not exist; use action='create' to add a new skill.",
    }
    assert calls == []
