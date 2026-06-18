from app.modules.automation.queue.celery_app import celery_app


def test_workload_queues_are_isolated():
    routes = celery_app.conf.task_routes
    assert routes["ai.*"]["queue"] == "ai"
    assert routes["documents.*"]["queue"] == "documents"
    assert routes["email.*"]["queue"] == "notifications"


def test_ai_run_worker_task_is_registered():
    celery_app.loader.import_task_module(
        "app.modules.automation.workers.tasks.ai_tasks"
    )
    assert "ai.execute_run" in celery_app.tasks
