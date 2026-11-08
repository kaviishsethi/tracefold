"""Fixed, versioned discovery presets and packs (docs/PRESET_PLAN.md).

A preset is search intent rendered separately for each provider from the approved public identity only:
``{name}`` (display name), ``{alias}`` (first public alias) and ``{domain}`` (official domain). No template reads
documents, filenames, results or model output, and no template uses Boolean operators (providers don't guarantee them).
A rendered plan stores every outbound field, so the preview is exactly what leaves the machine.
"""
from __future__ import annotations

from ..errors import ApiError

QUERY_TEMPLATE_VERSION = "company_queries_v3"
PROVIDERS = ("exa", "tavily")

# Budget shapes: (max searches, max results per search). Both fit the 40-request scan cap with extraction reserved:
# 4 + 20 + 16 fallbacks, or 8 + 20 + 12 fallbacks.
SHAPES = {"4x5": (4, 5), "8x3": (8, 3)}
MAX_SEARCHES = 8
MAX_RESULTS_PER_SEARCH = 5

# Public-site groups. Translated into each provider's documented domain filter.
SITE_GROUPS: dict[str, list[str]] = {
    "github": ["github.com", "gist.github.com"],
    "reddit": ["reddit.com"],
    "paste": ["pastebin.com", "paste.ee", "rentry.co", "ghostbin.cloud"],
    "code": ["github.com", "gist.github.com", "gitlab.com", "bitbucket.org"],
    "documents": ["scribd.com", "issuu.com", "docdroid.net", "yumpu.com", "slideshare.net", "speakerdeck.com"],
    "forums": ["reddit.com", "teamblind.com", "news.ycombinator.com"],
}

# Excluded from results by default (user-visible scope option). Company profile, dictionary and social pages seen as
# noise in the recorded runs; extend only with measured evidence (docs/PRESET_PLAN.md §6.3).
NOISE_DOMAINS_VERSION = "noise_v1"
NOISE_DOMAINS = sorted({
    "linkedin.com", "wikipedia.org", "tavily.com", "crunchbase.com", "trustpilot.com", "glassdoor.com",
    "merriam-webster.com", "dictionary.com", "youtube.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
})

EXA_CATEGORIES = ("news", "publication", "financial report", "personal site")
TAVILY_TOPICS = ("general", "news", "finance")


def _p(description, exa, tavily, *, needs=(), sites=None, mode="restrict", status="experimental", exclude_noise=True):
    return {"description": description, "exa": exa, "tavily": tavily, "needs": tuple(needs), "sites": sites,
            "include_mode": mode, "status": status, "exclude_noise": exclude_noise}


# status: benchmarked (found a benchmark target), experimental (no target found yet; explicit opt-in),
# legacy (v1/v2 wording kept for comparison and stored-plan compatibility).
PRESETS: dict[str, dict] = {
    # --- v3 catalog (docs/PRESET_PLAN.md §4) ---
    "leak_news": _p("News coverage quoting a leaked internal document.",
                    {"query": "news article quoting a leaked internal memo from {name}", "category": "news"},
                    {"query": '"{name}" leaked internal memo', "topic": "news", "exact_match": True},
                    status="benchmarked"),
    "leak_news_alias": _p("News coverage of a leaked internal document, under the first public alias.",
                          {"query": "news article quoting a leaked internal memo from {alias}", "category": "news"},
                          {"query": '"{alias}" leaked internal memo', "topic": "news", "exact_match": True},
                          needs=("alias",), status="benchmarked"),
    "leaked_email": _p("Published CEO or all-hands emails.",
                       {"query": "full text of an internal email sent to {name} employees", "category": "news"},
                       {"query": '"{name}" email to employees full text', "exact_match": True}, status="benchmarked"),
    "leaked_roadmap": _p("Reported roadmaps, plans and strategy documents.",
                         {"query": "leaked {name} product roadmap or strategy document", "category": "news"},
                         {"query": '"{name}" leaked roadmap', "exact_match": True}),
    "product_leaks": _p("Leaked specifications or hardware details of upcoming products, under the first public alias.",
                        {"query": "leaked specifications of an upcoming {alias} product", "category": "news"},
                        {"query": '"{alias}" leaked specs', "topic": "news", "exact_match": True}, needs=("alias",)),
    "leaked_deck": _p("Internal, investor or board slides posted publicly.",
                      {"query": "internal presentation slides from {name}"},
                      {"query": '"{name}" internal presentation slides', "exact_match": True},
                      sites=["documents"], mode="prefer"),
    "doc_sharing": _p("Documents uploaded to document-sharing sites.",
                      {"query": "document published by {name}"},
                      {"query": '"{name}"', "exact_match": True}, sites=["documents"]),
    "code_hosts_name": _p("Repositories, gists and issues naming the company.",
                          {"query": "source code repository from {name}"},
                          {"query": '"{name}"', "exact_match": True}, sites=["code"]),
    "code_hosts_domain": _p("Code and configuration files that mention the official domain.",
                            {"query": "configuration file referencing {domain}"},
                            {"query": '"{domain}" config', "exact_match": False}, needs=("domain",), sites=["code"]),
    "paste_sites": _p("Pastes naming the company or its domain.",
                      {"query": "{name} {domain}"},
                      {"query": '"{name}" {domain}', "exact_match": False}, needs=("domain",), sites=["paste"]),
    "policy_copies": _p("Republished company policies, handbooks and procedures.",
                        {"query": "{name} employee handbook or company policy document"},
                        {"query": '"{name}" policy handbook procedure', "exact_match": True}, status="benchmarked"),
    "security_docs": _p("Security policies, incident-response plans and audit documents.",
                        {"query": "{name} security policy or incident response plan document"},
                        {"query": '"{name}" security policy incident response', "exact_match": True},
                        status="benchmarked"),
    "breach_coverage": _p("Reporting on breaches and source-code leaks.",
                          {"query": "report on a data breach or source code leak at {name}", "category": "news"},
                          {"query": '"{name}" breach source code leak', "topic": "news", "exact_match": True}),
    "employee_forums": _p("Employee posts discussing internal material.",
                          {"query": "{name} employee discussion about internal documents"},
                          {"query": '"{name}" employees internal', "exact_match": True}, sites=["forums"]),
    "financial_filings": _p("Filings and reports quoting internal documents.",
                            {"query": "{name} financial report", "category": "financial report"},
                            {"query": '"{name}" annual report internal', "topic": "finance", "exact_match": True}),
    # --- legacy wording (v1/v2) ---
    "identity": _p("Company name plus official domain (or first alias) for disambiguation. Low yield.",
                   {"query": '"{name}" {hint}'}, {"query": '"{name}" {hint}'}, needs=("hint",), status="legacy"),
    "internal_docs": _p("v1: company name plus generic internal-document terms.",
                        {"query": '"{name}" internal memo document'}, {"query": '"{name}" internal memo document'},
                        status="legacy"),
    "source_config": _p("v1: company name plus generic source-code terms.",
                        {"query": '"{name}" source code configuration'}, {"query": '"{name}" source code configuration'},
                        status="legacy"),
    "leak_reports": _p("v2: company name plus leak-reporting terms.",
                       {"query": '"{name}" leaked internal memo'}, {"query": '"{name}" leaked internal memo'},
                       status="legacy"),
    "alias_leak_reports": _p("v2: first alias plus leak-reporting terms.",
                             {"query": '"{alias}" leaked internal memo'}, {"query": '"{alias}" leaked internal memo'},
                             needs=("alias",), status="legacy"),
    "public_sites": _p("v1: company name restricted to the user's selected sites.",
                       {"query": '"{name}"'}, {"query": '"{name}"'}, needs=("selected_scope",), status="legacy"),
}

# Evidence behind each status, from docs/benchmark/v3 (live runs 2026-11-08, 7 cases / 30 scans, scored by
# examples/preset_benchmark.py). A preset is "benchmarked" when, on at least one provider, it returned a page outside the
# company's own domain that matched a benchmark reference document locally (≥ 12 normalized tokens), with no
# negative-control match. Known copies are used for recall; any verified match counts as evidence. Mock-leak cases count:
# their references contain verbatim passages of a real reported leak, and the matched pages are real public pages.
BENCHMARK_VERSION = "v3-2026-11-08c"
BENCHMARK = {
    "leak_news": {"cases_hit": ["nothing"], "providers_hit": ["exa"]},
    "leak_news_alias": {"cases_hit": ["nothing"], "providers_hit": ["exa"]},
    "security_docs": {"cases_hit": ["civicactions", "sourcegraph"], "providers_hit": ["exa", "tavily"]},
    "policy_copies": {"cases_hit": ["sourcegraph"], "providers_hit": ["tavily"]},
    "leaked_email": {"cases_hit": ["mock_apple_memo"], "providers_hit": ["exa"]},
}

PACKS: dict[str, dict] = {
    "leak_watch": {"description": "Reported leaks of internal documents.", "shape": "4x5",
                   "presets": ["leak_news", "leak_news_alias"]},
    "document_copies": {"description": "Republished documents: decks, shared files, policies, security documents.",
                        "shape": "8x3", "presets": ["leaked_deck", "doc_sharing", "policy_copies", "security_docs"]},
    "code_exposure": {"description": "Source code, configuration and pastes.", "shape": "8x3",
                      "presets": ["code_hosts_name", "code_hosts_domain", "paste_sites", "breach_coverage"]},
    "broad_triage": {"description": "A first run for a new company.", "shape": "8x3",
                     "presets": ["leak_news", "leaked_email", "policy_copies", "code_hosts_name"]},
}


def _values(profile: dict) -> dict:
    aliases = profile.get("public_aliases") or []
    hint = profile.get("official_domain") or (f'"{aliases[0]}"' if aliases else "")
    return {"name": profile["display_name"], "alias": aliases[0] if aliases else "", "domain": profile.get("official_domain") or "",
            "hint": hint}


def missing_needs(preset: dict, profile: dict, scope_mode: str) -> str | None:
    v = _values(profile)
    for n in preset["needs"]:
        if n == "selected_scope" and scope_mode != "selected":
            return "needs scope.mode 'selected'"
        if n in ("alias", "domain", "hint") and not v[n]:
            return {"alias": "needs a public alias", "domain": "needs an official domain",
                    "hint": "needs an official domain or a public alias"}[n]
    return None


def _domains(groups: list[str]) -> list[str]:
    return sorted({d for g in groups for d in SITE_GROUPS[g]})


def render(preset_id: str, provider: str, profile: dict, scope: dict, num_results: int) -> dict:
    """One outbound search, fully specified. Raises ApiError when user scope and preset sites don't overlap."""
    pr = PRESETS[preset_id]
    spec = pr[provider]
    q = spec["query"].format(**_values(profile)).strip()
    user_sites = _domains(scope["site_groups"]) if scope["mode"] == "selected" else None
    own_sites = _domains(pr["sites"]) if pr["sites"] else None
    include, mode = None, None
    if own_sites is not None and user_sites is not None:
        include = sorted(set(own_sites) & set(user_sites))
        if not include:
            raise ApiError(422, "invalid_query_plan", f"Preset {preset_id} searches sites outside the selected scope.")
        mode = "restrict"
    elif own_sites is not None:
        include, mode = own_sites, pr["include_mode"]
    elif user_sites is not None:
        include, mode = user_sites, "restrict"
    if provider == "exa" and mode == "prefer":
        include, mode = None, None  # Exa has no "prefer" mode; search the open web with exclusions instead
    exclude: list[str] = []
    if mode != "restrict":
        if scope["exclude_official_domain"] and profile.get("official_domain"):
            exclude.append(profile["official_domain"])
        if scope["exclude_noise"] and pr["exclude_noise"]:
            exclude += [d for d in NOISE_DOMAINS if d not in (include or [])]
    out = {"template_id": preset_id, "provider": provider, "query": q, "num_results": num_results,
           "include_domains": include, "include_domains_mode": mode if provider == "tavily" else None,
           "exclude_domains": sorted(set(exclude)) or None, "category": None, "topic": None, "exact_match": None}
    if provider == "exa":
        out["category"] = spec.get("category")
    else:
        out["topic"] = spec.get("topic") or "general"
        out["exact_match"] = bool(spec.get("exact_match", False))
    return out


def build_plan(profile: dict, presets: list[str] | None, pack: str | None, providers: list[str] | None,
               scope: dict, results_per_query: int | None, allow_experimental: bool = False) -> dict:
    """Render the exact outbound searches. Deterministic: same inputs → identical plan."""
    if (presets is None) == (pack is None):
        raise ApiError(422, "invalid_query_plan", "Give exactly one of presets or pack.")
    omitted: list[dict] = []
    if pack is not None:
        if pack not in PACKS:
            raise ApiError(422, "invalid_query_plan", f"pack must be one of: {', '.join(PACKS)}.")
        chosen = list(PACKS[pack]["presets"])
        shape = PACKS[pack]["shape"]
    else:
        chosen = list(dict.fromkeys(presets or []))
        shape = None
    providers = list(dict.fromkeys(providers or list(PROVIDERS)))
    if not chosen or any(t not in PRESETS for t in chosen):
        raise ApiError(422, "invalid_query_plan", f"presets must be chosen from: {', '.join(PRESETS)}.")
    if not providers or any(p not in PROVIDERS for p in providers):
        raise ApiError(422, "invalid_query_plan", f"providers must be chosen from: {', '.join(PROVIDERS)}.")
    if scope["mode"] not in ("broad", "selected"):
        raise ApiError(422, "invalid_query_plan", "scope.mode must be 'broad' or 'selected'.")
    groups = list(dict.fromkeys(scope.get("site_groups") or []))
    if any(g not in SITE_GROUPS for g in groups):
        raise ApiError(422, "invalid_query_plan", f"scope.site_groups must be chosen from: {', '.join(SITE_GROUPS)}.")
    if scope["mode"] == "selected" and not groups:
        raise ApiError(422, "invalid_query_plan", "Selected scope needs at least one site group.")
    if scope["mode"] == "broad" and groups:
        raise ApiError(422, "invalid_query_plan", "Broad scope does not take site groups.")
    scope = {"mode": scope["mode"], "site_groups": groups, "exclude_official_domain": bool(scope.get("exclude_official_domain", True)),
             "exclude_noise": bool(scope.get("exclude_noise", True))}
    usable = []
    for t in chosen:
        why = missing_needs(PRESETS[t], profile, scope["mode"])
        if why is None and pack is not None and PRESETS[t]["status"] == "experimental" and not allow_experimental:
            why = "experimental preset (no benchmark target found yet); set include_experimental to use it"
        if why:
            if pack is None:
                raise ApiError(422, "invalid_query_plan", f"Preset {t} {why}.")
            omitted.append({"preset": t, "reason": why})
        else:
            usable.append(t)
    if not usable:
        raise ApiError(422, "invalid_query_plan", "No preset in this pack can be used with this profile.")
    n = len(usable) * len(providers)
    if shape is None:
        shape = "4x5" if n <= 4 else "8x3"
    max_s, max_r = SHAPES[shape]
    if n > max_s:
        raise ApiError(422, "invalid_query_plan",
                       f"A plan may issue at most {MAX_SEARCHES} searches (8 with up to 3 results each, or 4 with up to 5).")
    rpq = max_r if results_per_query is None else results_per_query
    if not 1 <= rpq <= max_r:
        raise ApiError(422, "invalid_query_plan", f"results_per_query must be 1-{max_r} for {n} searches.")
    searches = []
    for t in usable:
        for prov in providers:
            searches.append({"query_id": f"q{len(searches) + 1}", **render(t, prov, profile, scope, rpq),
                             "preset_status": PRESETS[t]["status"]})
    return {"template_version": QUERY_TEMPLATE_VERSION, "noise_domains_version": NOISE_DOMAINS_VERSION, "pack": pack,
            "omitted_presets": omitted, "searches": searches,
            "scope": {**scope, "include_domains": _domains(groups) if scope["mode"] == "selected" else None},
            "limits": {"shape": shape, "max_searches": max_s, "results_per_query": rpq,
                       "max_returned_candidates": len(searches) * rpq}}


def catalog() -> dict:
    return {"template_version": QUERY_TEMPLATE_VERSION, "noise_domains_version": NOISE_DOMAINS_VERSION,
            "noise_domains": NOISE_DOMAINS, "site_groups": SITE_GROUPS,
            "benchmark_version": BENCHMARK_VERSION,
            "presets": [{"preset_id": k, "description": v["description"], "status": v["status"], "needs": list(v["needs"]),
                         "benchmark": BENCHMARK.get(k),
                         "site_groups": v["sites"] or [], "include_mode": v["include_mode"] if v["sites"] else None,
                         "exa": dict(v["exa"]), "tavily": dict(v["tavily"])} for k, v in PRESETS.items()],
            "packs": [{"pack_id": k, **v} for k, v in PACKS.items()],
            "shapes": {k: {"max_searches": a, "max_results_per_search": b} for k, (a, b) in SHAPES.items()}}
