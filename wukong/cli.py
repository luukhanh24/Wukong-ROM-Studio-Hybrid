from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from studio_paths import CONTENT_ROOT, JOBS_ROOT, WORKSPACE_ROOT

from .executor import LocalJobExecutor
from .github import GitHubActionsAdapter
from .models import BuildRecipe, Identity, RecipeValidationError
from .orchestrator import FileJobStore, HybridOrchestrator, OrchestrationError
from .routing import RunnerInventory, RunnerUnavailableError
from .runtime import HybridRuntime
from .security import validate_recipe_access
from .source_probe import probe_http_source


def configure_utf8_stdio() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _recipe(path: str) -> BuildRecipe:
    return BuildRecipe.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _identity(args: argparse.Namespace) -> Identity:
    return Identity(args.channel, args.subject, args.role)


def _github_adapter_from_env() -> GitHubActionsAdapter | None:
    token = os.environ.get("WUKONG_GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repository = os.environ.get("WUKONG_GITHUB_REPOSITORY") or os.environ.get("GITHUB_REPOSITORY")
    if not token or not repository or "/" not in repository:
        return None
    owner, name = repository.split("/", 1)
    return GitHubActionsAdapter(owner, name, token)


def _inventory() -> RunnerInventory:
    github = _github_adapter_from_env()
    return github.runner_inventory() if github else RunnerInventory(False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wukong", description="Wukong ROM Studio hybrid CLI")
    parser.add_argument("--jobs-root", default=str(JOBS_ROOT / "hybrid"))
    parser.add_argument("--workspace-root", default=str(WORKSPACE_ROOT / ".wkstudio" / "hybrid"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--recipe", required=True)

    probe = subparsers.add_parser("probe-source")
    probe.add_argument("uri")

    for name in ("submit",):
        command = subparsers.add_parser(name)
        command.add_argument("--recipe", required=True)
        command.add_argument("--job-id")
        _identity_arguments(command)

    for name in ("inspect", "events", "cancel", "resume", "execute"):
        command = subparsers.add_parser(name)
        command.add_argument("job_id")
        if name != "execute":
            _identity_arguments(command)
        if name == "events":
            command.add_argument("--after", type=int, default=0)

    dispatch = subparsers.add_parser("dispatch")
    dispatch.add_argument("--recipe-ref", required=True)
    dispatch.add_argument("--workflow", default="wukong-build.yml")
    dispatch.add_argument("--ref", default="main")
    dispatch.add_argument("--job-id")
    return parser


def _identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--channel", required=True, choices=["windows", "telegram", "actions", "cli"])
    parser.add_argument("--subject", required=True)
    parser.add_argument("--role", default="user", choices=["admin", "user"])


def main(argv: Sequence[str] | None = None) -> int:
    configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        jobs_root = Path(args.jobs_root)
        workspace_root = Path(args.workspace_root)
        store = FileJobStore(jobs_root)
        orchestrator = HybridOrchestrator(
            store=store,
            workspace_root=workspace_root,
            inventory_provider=_inventory,
            access_validator=lambda recipe, identity: validate_recipe_access(
                recipe,
                identity,
                local_roots=[CONTENT_ROOT, WORKSPACE_ROOT],
                allowed_remote=os.environ.get("WUKONG_RCLONE_REMOTE", "wukong-gdrive"),
            ),
        )
        if args.command == "validate":
            recipe = _recipe(args.recipe)
            decision = orchestrator.validate(recipe)
            _json({"ok": True, "recipeDigest": recipe.digest, "runner": decision.to_dict()})
        elif args.command == "probe-source":
            _json(probe_http_source(args.uri).to_dict())
        elif args.command == "submit":
            _json(orchestrator.submit(_recipe(args.recipe), _identity(args), job_id=args.job_id).to_dict())
        elif args.command == "inspect":
            _json(orchestrator.inspect(args.job_id, _identity(args)).to_dict())
        elif args.command == "events":
            _json({"events": [event.to_dict() for event in orchestrator.events(args.job_id, _identity(args), after=args.after)]})
        elif args.command == "cancel":
            current = orchestrator.inspect(args.job_id, _identity(args))
            cancelled = orchestrator.cancel(args.job_id, _identity(args))
            data_root = jobs_root.parent.parent if jobs_root.name == "hybrid" else jobs_root.parent
            HybridRuntime(
                orchestrator=orchestrator,
                store=store,
                workspace_root=workspace_root,
                data_root=data_root,
            ).cancel_external(current)
            _json(cancelled.to_dict())
        elif args.command == "resume":
            data_root = jobs_root.parent.parent if jobs_root.name == "hybrid" else jobs_root.parent
            runtime = HybridRuntime(
                orchestrator=orchestrator,
                store=store,
                workspace_root=workspace_root,
                data_root=data_root,
            )
            _json(runtime.resume(args.job_id, _identity(args)).to_dict())
        elif args.command == "execute":
            config = os.environ.get("WUKONG_RCLONE_CONFIG")
            executor = LocalJobExecutor(
                store=store,
                workspace_root=workspace_root,
                rclone_config=Path(config) if config else None,
            )
            manifest = executor.execute(args.job_id)
            _json(manifest.to_dict())
            return 0 if manifest.status.value == "succeeded" else 1
        elif args.command == "dispatch":
            github = _github_adapter_from_env()
            if not github:
                raise OrchestrationError("GitHub credentials are not configured")
            github.dispatch(
                args.workflow,
                recipe_ref=args.recipe_ref,
                job_id=args.job_id,
                ref=args.ref,
            )
            _json({"ok": True, "workflow": args.workflow, "recipeRef": args.recipe_ref})
        return 0
    except (OSError, json.JSONDecodeError, RecipeValidationError, OrchestrationError, RunnerUnavailableError) as exc:
        _json({"ok": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
