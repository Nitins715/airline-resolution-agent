import pytest
from rest_framework.test import APIClient
from django.urls import reverse
from django.core.management import call_command


@pytest.fixture(autouse=True)
def setup_data(db):
    call_command('seed_assignment_data')
    return APIClient()


@pytest.mark.django_db
def test_health_check_api(setup_data):
    client = setup_data
    response = client.get('/api/health/')
    assert response.status_code == 200
    assert response.data['status'] == 'healthy'
    assert response.data['simulated_date'] == '2026-09-23'


@pytest.mark.django_db
def test_index_page(setup_data):
    client = setup_data
    response = client.get('/')
    assert response.status_code == 200
    assert b"Airline Resolution Assistant" in response.content
    assert b"Priya Nair" in response.content
    assert b"Arvind Kulkarni" in response.content
    assert b"Meher Kaur" in response.content


@pytest.mark.django_db
def test_customer_list_api(setup_data):
    client = setup_data
    response = client.get('/api/customers/')
    assert response.status_code == 200
    assert len(response.data) == 3
    names = [c['name'] for c in response.data]
    assert 'Priya Nair' in names
    assert 'Arvind Kulkarni' in names
    assert 'Meher Kaur' in names


@pytest.mark.django_db
def test_chat_api_scenario_1(setup_data):
    client = setup_data
    payload = {
        "pnr": "SK4821X",
        "message": "My flight SK-204 was cancelled. I want a full refund and also a free upgrade to business class on my return flight."
    }
    response = client.post('/api/chat/', data=payload, format='json')
    assert response.status_code == 200
    data = response.data
    assert data['customer_name'] == 'Priya Nair'
    assert data['conversation_status'] == 'ESCALATED'
    assert len(data['resolutions']) >= 1
    assert len(data['escalations']) >= 1


@pytest.mark.django_db
def test_chat_api_scenario_2(setup_data):
    client = setup_data
    payload = {
        "pnr": "TR1190B",
        "message": "My flight SK-118 is delayed 4 hours. Can I get a hotel room?"
    }
    response = client.post('/api/chat/', data=payload, format='json')
    assert response.status_code == 200
    data = response.data
    assert data['customer_name'] == 'Arvind Kulkarni'
    # Meal voucher and lounge access provided
    res_types = [r['action_type'] for r in data['resolutions']]
    assert 'MEAL_VOUCHER_500' in res_types
    assert 'MEAL_VOUCHER_AND_LOUNGE' in res_types


@pytest.mark.django_db
def test_chat_api_scenario_3(setup_data):
    client = setup_data
    payload = {
        "pnr": "WL7742",
        "message": "My flight SK-305 is delayed 6 hours. I want a full night hotel and to switch flights with a ₹2,000 fare difference waiver."
    }
    response = client.post('/api/chat/', data=payload, format='json')
    assert response.status_code == 200
    data = response.data
    assert data['customer_name'] == 'Meher Kaur'
    assert data['conversation_status'] == 'ESCALATED'
    esc_reasons = [e['reason'] for e in data['escalations']]
    assert 'FARE_WAIVER_EXCEEDS_1500' in esc_reasons


@pytest.mark.django_db
def test_scenario_runner_api(setup_data):
    client = setup_data
    response = client.post('/api/scenarios/run/', data={'scenario': 'all'}, format='json')
    assert response.status_code == 200
    assert response.data['scenarios_executed'] == 3
    assert response.data['results']['scenario_1_priya_nair']['status'] == 'PASSED'
    assert response.data['results']['scenario_2_arvind_kulkarni']['status'] == 'PASSED'
    assert response.data['results']['scenario_3_meher_kaur']['status'] == 'PASSED'
