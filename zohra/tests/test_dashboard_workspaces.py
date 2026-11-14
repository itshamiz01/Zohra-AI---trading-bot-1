from pathlib import Path
import sqlite3
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from zohra.api.app import create_app
from zohra.analytics import workspace_data


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.mark.parametrize('path', [
    '/api/v1/os/telemetry', '/api/v1/consensus', '/api/v1/agents',
    '/api/v1/trades/open', '/api/v1/trades/history', '/api/v1/research',
    '/api/v1/memory?q=gold', '/api/v1/learning', '/api/v1/automation/workflows',
    '/api/v1/voice/diagnostics', '/api/v1/vision/diagnostics', '/api/v1/plugins',
    '/api/v1/evolution/health', '/api/v1/evolution/recommendations', '/api/v1/settings'])
def test_workspace_endpoint(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)


@pytest.mark.parametrize('path', [
    '/api/v1/advanced/exposure', '/api/v1/advanced/correlation',
    '/api/v1/advanced/risk-concentration', '/api/v1/advanced/margin-health',
    '/api/v1/advanced/performance/strategies', '/api/v1/advanced/missed-opportunities',
    '/api/v1/advanced/false-signals', '/api/v1/advanced/broker-performance',
    '/api/v1/advanced/ai-insights', '/api/v1/advanced/system-health',
    '/api/v1/advanced/debrief', '/api/v1/advanced/monte-carlo',
    '/api/v1/learning/patterns', '/api/v1/learning/recommendations',
    '/api/v1/memory/recent', '/api/v1/memory/search?q=gold',
])
def test_advanced_reporting_endpoints(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text


def test_voice_health_requires_ready_transcription_and_synthesis(client):
    with patch('zohra.api.voice_router.gateway', None):
        report = client.get('/api/v1/voice/diagnostics').json()['diagnostics']
    assert report['status'] == 'degraded'
    assert report['components']['speech_recognition'] in {'unavailable', 'not_initialized'}


def test_simulation_endpoint_validates_payload(client):
    for payload in [{'lot_mult': 'oops'}, {'lot_mult': -1}, {'stop_equity': 150}, {'disable_usd_jpy': 'oops'}]:
        assert client.post('/api/v1/advanced/simulate-risk', json=payload).status_code == 422


def test_workspace_alias_serves_canonical_dashboard(client):
    assert client.get('/workspace').text == client.get('/dashboard').text


def test_memory_reads_real_records_and_literal_search(tmp_path, monkeypatch):
    path = tmp_path / 'memory.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE semantic_memory (id INTEGER, text TEXT)')
        conn.executemany('INSERT INTO semantic_memory VALUES (?, ?)', [(1, 'gold'), (2, '100% confidence')])
    monkeypatch.setattr(workspace_data.config, 'DB_PATH', str(path))
    assert workspace_data.memory_snapshot('gold')['total_memories'] == 1
    assert workspace_data.memory_snapshot('%')['total_memories'] == 1
    assert workspace_data.memory_snapshot('missing')['total_memories'] == 0


def test_disconnected_trade_actions_do_not_call_broker(client):
    with patch('zohra.api.app.mt5_broker') as broker:
        broker.is_connected.return_value = False
        assert client.post('/api/v1/commands/close/123').status_code == 503
        assert client.post('/api/v1/commands/close-all').status_code == 503
        broker.close_trade.assert_not_called()
        broker.close_all_positions.assert_not_called()


def test_paper_mode_blocks_connected_broker_actions(client):
    with patch('zohra.api.app.mt5_broker') as broker:
        broker.is_connected.return_value = True
        assert client.post('/api/v1/commands/close/123').status_code == 403
        assert client.post('/api/v1/commands/close-all').status_code == 403
        broker.close_trade.assert_not_called()
        broker.close_all_positions.assert_not_called()


def test_ai_close_all_uses_the_same_broker_permission_gate(client):
    with patch('zohra.api.app.mt5_broker') as broker:
        broker.is_connected.return_value = True
        response = client.post('/api/v1/commands/ai', json={'command': 'close all'})
        assert response.status_code == 403
        broker.close_all_positions.assert_not_called()


def test_fleet_and_risk_gates_do_not_invent_available_account_data(client):
    with patch('zohra.api.app.mt5_broker') as broker:
        broker.is_connected.return_value = False
        fleet = client.get('/api/v1/fleet').json()
        gates = client.get('/api/v1/gates').json()

    assert all(account['equity'] is None for account in fleet['accounts'])
    assert all('terminal_path' not in account for account in fleet['accounts'])
    assert all(not account['trade_allowed'] for account in gates['account_gates'])


def test_capital_allocation_uses_no_fabricated_account_or_asset_splits(client):
    with patch('zohra.api.app.mt5_broker') as broker:
        broker.is_connected.return_value = False
        payload = client.get('/api/v1/capital-allocation').json()

    assert payload['account_splits'] == []
    assert payload['asset_splits'] == []


def test_unconfigured_plugin_marketplace_is_explicit(client):
    payload = client.get('/api/v1/plugins/marketplace').json()
    assert payload['status'] == 'unavailable'
    assert payload['plugins'] == []


def test_settings_reject_invalid_limits(client):
    assert client.post('/api/v1/settings', json={'risk_per_trade_pct': 5}).status_code == 422
    assert client.post('/api/v1/settings', json={'max_open_positions': -1}).status_code == 422


def test_vision_diagnostics_do_not_capture(client):
    with patch('zohra.api.vision_router.capture_manager.capture_frame') as capture:
        assert client.get('/api/v1/vision/diagnostics').status_code == 200
        capture.assert_not_called()


def test_empty_fleet_has_no_invented_equity(monkeypatch):
    from zohra.analytics import telemetry_provider
    monkeypatch.setattr(telemetry_provider, 'fleet_snapshots', lambda: {})
    data = telemetry_provider.get_trading_telemetry()
    assert data['equity'] is None
    assert data['daily_pnl'] is None
    assert data['status'] == 'UNAVAILABLE'


def test_unknown_workflow_is_rejected(client):
    assert client.post('/api/v1/automation/trigger', json={'command':'invent unsupported job'}).status_code == 422


def test_system_workflow_returns_measurements(client):
    response = client.post('/api/v1/automation/trigger', json={'command':'system status'})
    assert response.status_code == 200, response.text
    workflows = client.get('/api/v1/automation/workflows').json()['workflows']
    workflow = next(w for w in workflows if w['workflow_id'] == response.json()['workflow_id'])
    assert workflow['status'] == 'COMPLETED'
    assert 'cpu_usage_pct' in workflow['steps'][0]['result']


def test_dashboard_tab_contract_is_backed_by_live_routes():
    dashboard = (Path(__file__).parents[1] / 'api' / 'dashboard.html').read_text(encoding='utf-8')
    workspaces = (Path(__file__).parents[1] / 'api' / 'static' / 'workspaces.js').read_text(encoding='utf-8')
    expected_views = {
        'command-center', 'dashboard', 'ai-agents', 'trading', 'research', 'memory',
        'learning', 'automation', 'voice', 'vision', 'plugin', 'evolution', 'settings',
    }
    for view in expected_views:
        assert f'id="nav-{view}"' in dashboard
        assert f'id="view-{view}"' in dashboard
    for route in (
        '/api/v1/research', '/api/v1/memory', '/api/v1/learning',
        '/api/v1/automation/workflows', '/api/v1/voice/diagnostics',
        '/api/v1/vision/diagnostics', '/api/v1/plugins',
        '/api/v1/evolution/health', '/api/v1/settings',
    ):
        assert route in workspaces
