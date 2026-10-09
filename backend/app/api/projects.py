"""프로젝트(블록) — 워크스페이스 안의 블록 하나. 조립 트리와 작업이 프로젝트에 속한다.

/workspaces/{workspace_id}/projects
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import NOT_FOUND, StoreDep, WorkspaceDep
from app.schemas import AssemblyNode, Project, ProjectCreate

router = APIRouter(responses=NOT_FOUND)  # 모든 경로가 워크스페이스(·프로젝트) 하위 — 없으면 404


def get_project(project_id: str, workspace: WorkspaceDep, store: StoreDep) -> Project:
    """해당 워크스페이스의 프로젝트만 찾는다 — 다른 워크스페이스의 프로젝트 id 면 404."""
    project = store.get_project(workspace.id, project_id)
    if project is None:
        raise HTTPException(404, f"프로젝트를 찾을 수 없습니다: {project_id}")
    return project


ProjectDep = Annotated[Project, Depends(get_project)]


@router.get("")
def list_projects(workspace: WorkspaceDep, store: StoreDep) -> list[Project]:
    """생성 순 (오래된 것부터)"""
    return store.list_projects(workspace.id)


@router.post("", status_code=201)
def create_project(body: ProjectCreate, workspace: WorkspaceDep, store: StoreDep) -> Project:
    """새 프로젝트 — 조립 트리·작업이 비어 있다."""
    return store.create_project(workspace.id, body)


@router.get("/{project_id}")
def read_project(project: ProjectDep) -> Project:
    return project


# ── 조립 트리 ──

@router.get("/{project_id}/assembly-tree")
def get_assembly_tree(project: ProjectDep, store: StoreDep) -> list[AssemblyNode]:
    return store.get_assembly_tree(project.workspace_id, project.id)
