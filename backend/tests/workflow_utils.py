from __future__ import annotations

VALID_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
        {
            "id": "n2",
            "type": "human_review",
            "data": {
                "assignee_mode": "queue",
                "assignee_department_id": "22222222-2222-2222-2222-222222222222",
                "sla_hours": 24,
            },
        },
        {"id": "n3", "type": "end", "data": {}},
    ],
    "edges": [
        {"source": "n1", "target": "n2"},
        {"source": "n2", "target": "n3"},
    ],
}
