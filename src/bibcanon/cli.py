"""Typer CLI entrypoint for bibcanon: `serve`, `check`, `fix`, `cache`."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import webbrowser
from pathlib import Path
from typing import Annotated, Literal

import typer
import uvicorn
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from bibcanon.config import load_config
from bibcanon.core.bib_parser import (
    parse_bib_file,
    splice_bib_document,
    write_bib_with_backup,
)
from bibcanon.core.pipeline import run_verification_pipeline
from bibcanon.models import (
    DecisionPayload,
    EntryAuditResult,
    StyleMode,
    VerificationStatus,
    WarningCode,
)
from bibcanon.server.app import create_app
from bibcanon.server.auth import CloudSecurityConfig
from bibcanon.storage.cache import BibCache

app = typer.Typer(
    name="bibcanon",
    help="Lossless BibTeX verifier, preprint upgrader, and canonical publisher BibTeX workbench.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()

_STATUS_LABELS: dict[VerificationStatus, str] = {
    VerificationStatus.VERIFIED_CANONICAL: "[green]✅ 已核验·标准版[/green]",
    VerificationStatus.PREPRINT_UPGRADE: "[cyan]🔄 可转正升级[/cyan]",
    VerificationStatus.VERIFIED_PREPRINT_ONLY: "[blue]📄 已核验·仅预印本[/blue]",
    VerificationStatus.METADATA_MISMATCH: "[yellow]⚠️ 信息出入警告[/yellow]",
    VerificationStatus.SUSPECTED_HALLUCINATION: "[bold red]❌ 疑似虚假/查无此文[/bold red]",
    VerificationStatus.ERROR: "[magenta]⚡ 网络异常[/magenta]",
    VerificationStatus.UNPROCESSED: "[dim]⏳ 待处理[/dim]",
}


def _run_cli_pipeline(
    bib_file: Path,
    force_refresh: bool = False,
) -> tuple[object, list[EntryAuditResult]]:
    if not bib_file.exists() or not bib_file.is_file():
        console.print(f"[bold red]错误:[/bold red] 找不到文件 {bib_file}")
        raise typer.Exit(code=2)

    doc = parse_bib_file(bib_file)
    cfg = load_config()
    cache = BibCache(ttl_days=cfg.cache_ttl_days)

    if not doc.entries:
        console.print("[yellow]提示:[/yellow] 该 .bib 文件未包含可解析的标准引用条目。")
        return doc, []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(
            f"正在核验 {bib_file.name} ({len(doc.entries)} 条引用)...",
            total=len(doc.entries),
        )

        def _on_update(entry: EntryAuditResult, completed: int, total: int) -> None:
            progress.update(
                task_id,
                completed=completed,
                description=f"正在核验 [{completed}/{total}] {entry.cite_key}",
            )

        results = asyncio.run(
            run_verification_pipeline(
                doc,
                config=cfg,
                cache=cache,
                force_refresh=force_refresh,
                on_entry_updated=_on_update,
            )
        )

    return doc, results


def _print_audit_summary_table(results: list[EntryAuditResult]) -> None:
    table = Table(title="bibcanon 参考文献核验汇总报告", show_lines=False)
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("Citation Key", style="bold", no_wrap=True)
    table.add_column("状态", no_wrap=True)
    table.add_column("置信度", justify="right")
    table.add_column("推荐来源 / 场馆")
    table.add_column("诊断说明")

    for r in results:
        cand = r.candidates[r.selected_candidate_idx or 0] if r.candidates else None
        origin_info = "-"
        if cand is not None:
            venue_disp = cand.canonical_venue_id or cand.matched_venue or ""
            yr_disp = str(cand.matched_year) if cand.matched_year else ""
            origin_info = f"{cand.bibtex_origin} ({venue_disp} {yr_disp})".strip()

        notes = "; ".join(w.message for w in r.warnings) if r.warnings else ""
        table.add_row(
            str(r.entry_index + 1),
            r.cite_key,
            _STATUS_LABELS.get(r.status, r.status.value),
            f"{r.confidence:.1f}",
            origin_info,
            notes,
        )

    console.print(table)

    counts: dict[VerificationStatus, int] = {}
    dup_count = 0
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
        if any(w.code == WarningCode.DUPLICATE_IN_BIB for w in r.warnings):
            dup_count += 1

    console.print(
        f"\n[bold]统计汇总:[/bold] 共 {len(results)} 条 | "
        f"✅ 标准版 {counts.get(VerificationStatus.VERIFIED_CANONICAL, 0)} | "
        f"🔄 可转正 {counts.get(VerificationStatus.PREPRINT_UPGRADE, 0)} | "
        f"📄 纯预印本 {counts.get(VerificationStatus.VERIFIED_PREPRINT_ONLY, 0)} | "
        f"⚠️ 信息出入 {counts.get(VerificationStatus.METADATA_MISMATCH, 0)} | "
        f"❌ 疑似虚假 {counts.get(VerificationStatus.SUSPECTED_HALLUCINATION, 0)} | "
        f"🔁 重复条目 {dup_count} | "
        f"⚡ 网络异常 {counts.get(VerificationStatus.ERROR, 0)}"
    )


def _find_available_port(host: str, preferred_port: int, max_tries: int = 20) -> int:
    """Return `preferred_port` if bindable, otherwise step upward to the next free port."""
    for offset in range(max_tries):
        candidate = preferred_port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue
    return preferred_port


@app.command("serve")
def serve_cmd(
    bib_file: Annotated[
        Path | None,
        typer.Argument(help="可选：启动后自动加载的本地 .bib 文件路径（仅本地单机模式可用）"),
    ] = None,
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="服务监听端口"),
    ] = 8765,
    host: Annotated[
        str | None,
        typer.Option("--host", help="监听地址（本地默认 127.0.0.1；开启 --cloud 时默认 0.0.0.0）"),
    ] = None,
    cloud: Annotated[
        bool,
        typer.Option(
            "--cloud/--local",
            help="启用云端团队共享模式（默认监听 0.0.0.0、开启账号密码保护、禁用服务器本地磁盘读写）",
        ),
    ] = False,
    auth_user: Annotated[
        str,
        typer.Option("--auth-user", envvar="BIBCANON_USER", help="云端模式登录用户名"),
    ] = "admin",
    auth_pass: Annotated[
        str,
        typer.Option(
            "--auth-pass",
            envvar="BIBCANON_PASS",
            help="云端模式登录密码（未指定时自动生成一次性随机密码）",
        ),
    ] = "",
    no_browser: Annotated[
        bool,
        typer.Option("--no-browser", help="启动时不自动打开浏览器"),
    ] = False,
) -> None:
    """启动 FastAPI + Web Diff 审核工作台（支持本地单机模式与 --cloud 云端共享模式）。"""
    is_cloud = cloud or os.environ.get("BIBCANON_CLOUD", "").strip() in {"1", "true", "yes"}
    effective_host = host or ("0.0.0.0" if is_cloud else "127.0.0.1")

    resolved_bib: str | None = None
    if bib_file is not None and not is_cloud:
        p = bib_file.expanduser().resolve()
        if not p.exists() or not p.is_file():
            console.print(f"[bold red]错误:[/bold red] 指定的 .bib 文件不存在: {p}")
            raise typer.Exit(code=2)
        resolved_bib = str(p)

    actual_port = _find_available_port(effective_host, port)
    if actual_port != port:
        console.print(
            f"[yellow]提示:[/yellow] 端口 {port} 已被占用，自动切换至可用端口 [bold]{actual_port}[/bold]"
        )

    display_host = "127.0.0.1" if effective_host == "0.0.0.0" else effective_host
    url = f"http://{display_host}:{actual_port}"

    sec = CloudSecurityConfig(
        enabled=is_cloud,
        username=auth_user,
        password=auth_pass,
    )

    if is_cloud:
        console.print(
            f"[bold green]bibcanon 云端团队共享模式启动中:[/bold green] http://0.0.0.0:{actual_port} "
            f"(登录用户名: [cyan]{sec.username}[/cyan])"
        )
        if sec.auto_generated_password:
            console.print(
                f"[bold yellow]未配置 BIBCANON_PASS，本次启动自动生成随机密码:[/bold yellow] "
                f"[bold white]{sec.password}[/bold white]"
            )
    else:
        console.print(f"[bold green]bibcanon 本地工作台启动中:[/bold green] {url}")
        if resolved_bib:
            console.print(f"[cyan]自动加载本地文件:[/cyan] {resolved_bib}")

    if not no_browser and not is_cloud:
        threading.Timer(0.9, lambda: webbrowser.open(url)).start()

    fastapi_app = create_app(initial_bib_path=resolved_bib, cloud_security=sec)
    uvicorn.run(fastapi_app, host=effective_host, port=actual_port, log_level="warning")


@app.command("check")
def check_cmd(
    bib_file: Annotated[Path, typer.Argument(help="待核验的单个 .bib 文件路径")],
    json_report: Annotated[
        Path | None,
        typer.Option("--json", help="可选：导出完整 JSON 核验报告路径"),
    ] = None,
    force_refresh: Annotated[
        bool,
        typer.Option("--force-refresh", help="忽略本地 SQLite 缓存强制重新查询"),
    ] = False,
) -> None:
    """核验单个 .bib 文件并输出彩色体检汇总表（若含疑似虚假条目返回退出码 1）。"""
    _, results = _run_cli_pipeline(bib_file.expanduser().resolve(), force_refresh=force_refresh)
    _print_audit_summary_table(results)

    if json_report is not None:
        out_path = json_report.expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [r.model_dump() for r in results]
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        console.print(f"[green]已导出 JSON 核验报告:[/green] {out_path}")

    if any(r.status == VerificationStatus.SUSPECTED_HALLUCINATION for r in results):
        raise typer.Exit(code=1)


@app.command("fix")
def fix_cmd(
    bib_file: Annotated[Path, typer.Argument(help="待修复规范化的单个 .bib 文件路径")],
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="输出的新 .bib 文件路径"),
    ] = None,
    in_place: Annotated[
        bool,
        typer.Option("--in-place", help="自动备份为 .bak 后直接写回原 .bib 文件"),
    ] = False,
    mode: Annotated[
        StyleMode,
        typer.Option("--mode", help="渲染模式: canonical (出版方原汁原味) 或 compact (会议缩写)"),
    ] = "canonical",
    min_confidence: Annotated[
        float,
        typer.Option("--min-confidence", help="自动替换的最低置信度阈值"),
    ] = 90.0,
    protect_title_case: Annotated[
        bool,
        typer.Option(
            "--protect-title-case/--no-protect-title-case",
            help="是否自动开启标题专有名词大小写幂等保护",
        ),
    ] = True,
    force_refresh: Annotated[
        bool,
        typer.Option("--force-refresh", help="忽略本地 SQLite 缓存强制重新查询"),
    ] = False,
) -> None:
    """自动替换高置信度无警告条目（保留存疑条目原样并列出需人工复核清单）。"""
    if output is not None and in_place:
        console.print("[bold red]错误:[/bold red] -o/--output 与 --in-place 不能同时指定。")
        raise typer.Exit(code=2)

    resolved_in = bib_file.expanduser().resolve()
    doc, results = _run_cli_pipeline(resolved_in, force_refresh=force_refresh)
    cfg = load_config()

    decisions: dict[str, DecisionPayload] = {}
    manual_review_keys: list[str] = []

    for r in results:
        has_serious_warning = any(w.severity in {"error", "warning"} for w in r.warnings)
        eligible = (
            r.status
            in {
                VerificationStatus.VERIFIED_CANONICAL,
                VerificationStatus.PREPRINT_UPGRADE,
                VerificationStatus.VERIFIED_PREPRINT_ONLY,
            }
            and r.confidence >= min_confidence
            and not has_serious_warning
            and bool(r.candidates)
        )
        if eligible:
            decisions[r.cite_key] = DecisionPayload(
                decision="accept",
                selected_candidate_idx=r.selected_candidate_idx or 0,
            )
        else:
            decisions[r.cite_key] = DecisionPayload(decision="keep_original")
            if r.status in {
                VerificationStatus.METADATA_MISMATCH,
                VerificationStatus.SUSPECTED_HALLUCINATION,
                VerificationStatus.ERROR,
            } or has_serious_warning:
                manual_review_keys.append(r.cite_key)

    spliced_text, stats = splice_bib_document(
        doc.raw_text,
        results,
        style_mode=mode,
        protect_title_case=protect_title_case,
        decisions_override=decisions,
        noise_blacklist=cfg.noise_field_blacklist,
    )

    _print_audit_summary_table(results)

    if in_place:
        bak = write_bib_with_backup(resolved_in, spliced_text)
        console.print(f"\n[green]💾 原文件已自动备份至:[/green] {bak}")
        console.print(f"[bold green]✨ 已就地更新文件:[/bold green] {resolved_in}")
    else:
        target_out = (
            output.expanduser().resolve()
            if output is not None
            else resolved_in.with_name(f"{resolved_in.stem}.fixed.bib")
        )
        target_out.parent.mkdir(parents=True, exist_ok=True)
        target_out.write_text(spliced_text, encoding="utf-8")
        console.print(f"\n[bold green]✨ 已写出修复后的文件:[/bold green] {target_out}")

    console.print(
        f"自动更新: [green]{stats.accepted_count}[/green] 条 | "
        f"原样保留: [yellow]{stats.kept_original_count}[/yellow] 条"
    )
    if manual_review_keys:
        console.print(
            f"[bold yellow]⚠️ 需人工复核的条目 ({len(manual_review_keys)}):[/bold yellow] "
            + ", ".join(manual_review_keys)
        )


@app.command("cache")
def cache_cmd(
    action: Annotated[
        Literal["stats", "clear"],
        typer.Argument(help="操作类型: stats (查看缓存统计) 或 clear (清理本地缓存)"),
    ] = "stats",
    scope: Annotated[
        Literal["all", "queries"],
        typer.Option("--scope", help="清理范围: all (全部) 或 queries (仅查询缓存)"),
    ] = "all",
) -> None:
    """查看或清理本地 SQLite 缓存。"""
    cfg = load_config()
    cache = BibCache(ttl_days=cfg.cache_ttl_days)

    if action == "stats":
        stats = cache.get_stats()
        size_kb = stats["db_size_bytes"] / 1024.0
        console.print("[bold]bibcanon 本地 SQLite 缓存状态[/bold]")
        console.print(f"  路径: {stats['db_path']}")
        console.print(f"  大小: {size_kb:.1f} KB")
        console.print(f"  查询缓存条数: {stats['query_cache_count']}")
        console.print(
            f"  CVF 目录缓存: {stats['cvf_toc_venues_count']} 个会议年份 / "
            f"{stats['cvf_toc_papers_count']} 篇论文链接"
        )
    else:
        deleted = cache.clear(scope=scope)
        console.print(f"[green]已清理缓存 ({scope}):[/green] 释放 {deleted} 条记录。")


if __name__ == "__main__":
    app()
