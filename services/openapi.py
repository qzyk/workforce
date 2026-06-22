"""
OpenAPI 3.0 spec auto-generat pentru API publica /bim/api/* (Faza 8).

Construieste schema din introspecting blueprint-ul bim_bp.
Endpoint-urile care folosesc @api_token_required sunt marcate ca atare.
"""

from __future__ import annotations

from flask import current_app


# Schemele de baza pentru raspunsuri tipice
COMMON_SCHEMAS = {
    'Error': {
        'type': 'object',
        'properties': {
            'error': {'type': 'string'},
        },
    },
    'IssueBIM': {
        'type': 'object',
        'properties': {
            'id': {'type': 'integer'},
            'cod': {'type': 'string'},
            'titlu': {'type': 'string'},
            'descriere': {'type': 'string', 'nullable': True},
            'tip': {'type': 'string', 'enum': ['defect', 'conflict_proiectare', 'neconformitate']},
            'severitate': {'type': 'string', 'enum': ['mica', 'medie', 'mare', 'critica']},
            'status': {'type': 'string', 'enum': ['deschis', 'in_lucru', 'rezolvat', 'verificat', 'inchis']},
            'bcf_topic_guid': {'type': 'string', 'nullable': True},
        },
    },
    'SensorReading': {
        'type': 'object',
        'required': ['valoare'],
        'properties': {
            'valoare': {'type': 'number', 'format': 'float'},
            'ts': {'type': 'string', 'format': 'date-time', 'nullable': True},
            'calitate': {'type': 'string', 'enum': ['ok', 'estimat', 'eroare', 'maintenance']},
            'meta': {'type': 'object', 'additionalProperties': True},
        },
    },
    'SensorState': {
        'type': 'object',
        'properties': {
            'id': {'type': 'integer'},
            'cod': {'type': 'string'},
            'tip': {'type': 'string'},
            'unitate': {'type': 'string'},
            'ultima_valoare': {'type': 'number', 'nullable': True},
            'ultima_citire_at': {'type': 'string', 'format': 'date-time', 'nullable': True},
            'is_alarming': {'type': 'boolean'},
        },
    },
    'CostBreakdown': {
        'type': 'object',
        'properties': {
            'element_bim_id': {'type': 'integer'},
            'total': {'type': 'number'},
            'by_categorie': {'type': 'object', 'additionalProperties': {'type': 'number'}},
        },
    },
}


# Endpoints publice documentate (subset relevant)
# Restul rutelor /bim/api/* sunt protejate cu session (login_required) si nu sunt
# expuse aici ca API publica.
PUBLIC_ENDPOINTS = [
    {
        'path': '/bim/api/sensors/ingest',
        'method': 'post',
        'summary': 'Ingest sensor reading (token-auth per senzor)',
        'auth': 'sensor_token',
        'requestBody': {'$ref': '#/components/schemas/SensorReading'},
        'responses': {
            '200': {'description': 'Ingest reusit',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'reading_id': {'type': 'integer'},
                            'alert_created': {'type': 'boolean'},
                            'alert_new': {'type': 'boolean'},
                            'threshold_violated': {'type': 'string', 'nullable': True},
                        }
                    }},
            '401': {'description': 'Token lipsa sau invalid',
                    'schema': {'$ref': '#/components/schemas/Error'}},
            '403': {'description': 'Feature dezactivat'},
        },
    },
    {
        'path': '/bim/api/element/{element_id}/state',
        'method': 'get',
        'summary': 'Current state senzori pentru un element',
        'auth': 'session',
        'parameters': [{'in': 'path', 'name': 'element_id', 'schema': {'type': 'integer'}, 'required': True}],
        'responses': {
            '200': {'description': 'OK',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'enabled': {'type': 'boolean'},
                            'count_sensors': {'type': 'integer'},
                            'sensors': {'type': 'array', 'items': {'$ref': '#/components/schemas/SensorState'}},
                        }
                    }},
        },
    },
    {
        'path': '/bim/api/sensor/{sensor_id}/history',
        'method': 'get',
        'summary': 'Time-series history pentru senzor',
        'auth': 'session',
        'parameters': [
            {'in': 'path', 'name': 'sensor_id', 'schema': {'type': 'integer'}, 'required': True},
            {'in': 'query', 'name': 'agg', 'schema': {'type': 'string', 'enum': ['raw', '1h', '1d']}, 'required': False},
            {'in': 'query', 'name': 'from', 'schema': {'type': 'string', 'format': 'date-time'}, 'required': False},
            {'in': 'query', 'name': 'to', 'schema': {'type': 'string', 'format': 'date-time'}, 'required': False},
        ],
        'responses': {'200': {'description': 'Time-series JSON'}},
    },
    {
        'path': '/bim/api/element/{element_id}/cost',
        'method': 'get',
        'summary': 'Breakdown cost pe element (5D)',
        'auth': 'session',
        'parameters': [{'in': 'path', 'name': 'element_id', 'schema': {'type': 'integer'}, 'required': True}],
        'responses': {'200': {'description': 'CostBreakdown', 'schema': {'$ref': '#/components/schemas/CostBreakdown'}}},
    },
    {
        'path': '/bim/api/santier/{santier_id}/visible-at',
        'method': 'get',
        'summary': 'ID-uri elemente vizibile la o data (4D)',
        'auth': 'session',
        'parameters': [
            {'in': 'path', 'name': 'santier_id', 'schema': {'type': 'integer'}, 'required': True},
            {'in': 'query', 'name': 'data', 'schema': {'type': 'string', 'format': 'date'}, 'required': False},
        ],
        'responses': {'200': {'description': 'JSON cu visible_element_ids'}},
    },
    {
        'path': '/bim/api/v1/issues',
        'method': 'get',
        'summary': 'Lista issues (API publica versionata cu token)',
        'auth': 'api_token bim:read',
        'parameters': [
            {'in': 'query', 'name': 'status', 'schema': {'type': 'string'}, 'required': False},
        ],
        'responses': {'200': {'description': 'Array IssueBIM',
                              'schema': {'type': 'array', 'items': {'$ref': '#/components/schemas/IssueBIM'}}}},
    },
]


def generate_openapi_spec(app=None) -> dict:
    """
    Genereaza dictul OpenAPI 3.0 complet (servabil ca JSON la /bim/api/openapi.json).
    """
    if app is None:
        app = current_app._get_current_object() if current_app else None

    spec = {
        'openapi': '3.0.3',
        'info': {
            'title': 'EDIFICO Workforce BIM/Digital Twin API',
            'version': '1.0.0',
            'description': (
                'API publica pentru integrari externe. Trei moduri de autentificare:\n'
                '- **session** (cookie Flask-Login) — pentru UI propriu\n'
                '- **sensor_token** (header X-Sensor-Token, per senzor) — pentru gateway-uri IoT\n'
                '- **api_token** (header Authorization: Bearer <token>) — pentru integrari programatice\n'
            ),
            'contact': {'name': 'EDIFICO Workforce'},
        },
        'servers': [{'url': '/'}],
        'components': {
            'schemas': COMMON_SCHEMAS,
            'securitySchemes': {
                'session': {'type': 'apiKey', 'in': 'cookie', 'name': 'session'},
                'sensor_token': {'type': 'apiKey', 'in': 'header', 'name': 'X-Sensor-Token'},
                'api_token': {'type': 'http', 'scheme': 'bearer'},
            },
        },
        'paths': {},
    }

    for ep in PUBLIC_ENDPOINTS:
        path = ep['path']
        method = ep['method']
        path_item = spec['paths'].setdefault(path, {})

        operation = {
            'summary': ep['summary'],
            'tags': [path.split('/')[2] if len(path.split('/')) > 2 else 'general'],
            'security': [_security_for(ep['auth'])],
            'responses': _build_responses(ep.get('responses', {})),
        }
        if 'parameters' in ep:
            operation['parameters'] = ep['parameters']
        if 'requestBody' in ep:
            operation['requestBody'] = {
                'content': {'application/json': {'schema': ep['requestBody']}},
            }
        path_item[method] = operation

    return spec


def _security_for(auth: str) -> dict:
    if auth == 'sensor_token':
        return {'sensor_token': []}
    if auth.startswith('api_token'):
        # api_token bim:read -> scope hint
        parts = auth.split(' ', 1)
        scopes = [parts[1]] if len(parts) > 1 else []
        return {'api_token': scopes}
    return {'session': []}


def _build_responses(responses: dict) -> dict:
    out = {}
    for code, info in responses.items():
        resp = {'description': info.get('description', '')}
        if 'schema' in info:
            resp['content'] = {'application/json': {'schema': info['schema']}}
        out[code] = resp
    return out
