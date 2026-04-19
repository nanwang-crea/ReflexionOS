import importlib
import warnings

from sqlalchemy.exc import MovedIn20Warning


def test_core_models_import_without_deprecation_warnings():
    import app.config as app_config
    import app.models.execution as execution_models
    import app.models.project as project_models
    import app.storage.models as storage_models

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(app_config)
        importlib.reload(project_models)
        importlib.reload(execution_models)
        importlib.reload(storage_models)

    relevant_warnings = [
        warning for warning in caught
        if issubclass(warning.category, (DeprecationWarning, MovedIn20Warning))
    ]

    assert relevant_warnings == []
