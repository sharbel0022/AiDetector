"""Reproduce the explicitly bounded, rights-audited historical TextLab pilot.

Network access is opt-in (--download/--generate). verify and build use archived
bytes. Metadata checks verify assertions and hashes, never legal rights or truth.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "data" / "pilot"
LICENSE_URL = "https://www.gutenberg.org/policy/license.html"
RIGHTS_REFERENCES = {
    "swedish-copyright-law.html": "https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/lag-1960729-om-upphovsratt-till-litterara-och_sfs-1960-729/",
    "prv-copyright-faq.html": "https://www.prv.se/sv/upphovsratt/om-upphovsratt/fragor-och-svar-om-upphovsratt/",
    "gutenberg-permission.html": "https://www.gutenberg.org/policy/permission.html",
}
OLLAMA = "http://127.0.0.1:11434"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_excerpt(value: str) -> str:
    """Whitespace folding only: no spelling, punctuation or OCR correction."""
    return " ".join(value.split())


def body_bounds(text: str) -> tuple[int, int]:
    start = re.search(r"^\*\*\* START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK .*?\*\*\*[^\n]*\n", text, re.M)
    end = re.search(r"^\*\*\* END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK .*?\*\*\*", text, re.M)
    if not start or not end or end.start() <= start.end():
        raise ValueError("Missing or reversed Gutenberg body markers")
    return start.end(), end.start()


def select_excerpts(text: str, start: int, end: int, count: int = 3,
                    minimum: int = 180, maximum: int = 300) -> list[dict]:
    """Select disjoint complete paragraphs at predeclared body fractions.

    If a paragraph is too long, retain a contiguous prefix ending at a sentence
    boundary; short paragraphs are joined. Offsets index decoded Unicode code
    points in the entire UTF-8-sig raw text, with newline translation disabled.
    """
    fractions = [.18, .48, .78]
    if count != 3:
        raise ValueError("The frozen pilot requires exactly three excerpts")
    result = []
    paragraphs = [(start + m.start(), start + m.end()) for m in re.finditer(r"\S[\s\S]*?(?=\r?\n\s*\r?\n|\Z)", text[start:end])]
    for fraction in fractions:
        target = start + int((end - start) * fraction)
        candidate = next((j for j, (a, b) in enumerate(paragraphs) if a >= target and (not result or a >= result[-1]["end"])), None)
        if candidate is None:
            raise ValueError("Insufficient non-overlapping source text")
        a, b = paragraphs[candidate]
        j = candidate
        while len(normalize_excerpt(text[a:b]).split()) < minimum and j + 1 < len(paragraphs):
            j += 1
            b = paragraphs[j][1]
        words = list(re.finditer(r"\S+", text[a:b]))
        if len(words) > maximum:
            # Prefer a sentence ending within the declared interval.
            stops = [m.end() for m in words[minimum - 1:maximum] if re.search(r'[.!?][\"\u201d\u201c\u00bb\u2019_]*$', m.group())]
            b = a + (stops[-1] if stops else words[maximum - 1].end())
        value = normalize_excerpt(text[a:b])
        if not minimum <= len(value.split()) <= maximum:
            raise ValueError("Excerpt outside frozen word range")
        result.append({"start": a, "end": b, "text": value, "words": len(value.split()), "fraction": fraction})
    return result


def audit_groups(rows: list[dict]) -> None:
    for field in ["author_id", "document_id", "source_group_id"]:
        seen = {}
        for row in rows:
            if row[field] in seen and seen[row[field]] != row["split"]:
                raise ValueError(f"Split leakage in {field}: {row[field]}")
            seen[row[field]] = row["split"]


def verify_raw(source: dict, raw: bytes) -> None:
    if sha256(raw) != source["raw_sha256"]:
        raise ValueError(f"Raw SHA256 mismatch: {source.get('raw_path')}")


def verify_excerpt(raw_text: str, excerpt: dict) -> None:
    if normalize_excerpt(raw_text[excerpt["start"]:excerpt["end"]]) != excerpt["text"]:
        raise ValueError("Source excerpt reconstruction mismatch")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf8")


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "TextLabHistoricalPilot/1.0 (rights-audit; contact via repository)"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def clean_html(value: str) -> str:
    return normalize_excerpt(html.unescape(re.sub(r"<[^>]*>", " ", value)))


def catalog_contributors(page: str) -> list[dict]:
    result = []
    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", page, re.S):
        role = re.search(r"<th[^>]*>(.*?)</th>", row, re.S)
        if not role or clean_html(role[1]) not in ["Author", "Editor", "Illustrator", "Translator", "Contributor", "Author of introduction"]:
            continue
        value = re.search(r"<td\b[^>]*>(.*?)</td>", row, re.S)
        if value:
            name = clean_html(value[1])
            dates = re.search(r"\b\d{4}[-\u2013](\d{4})\b", name)
            result.append({"role": clean_html(role[1]), "name_dates": name, "death_year": int(dates[1]) if dates else None})
    return result


def author_body_bounds(identifier: int, text: str) -> tuple[int, int]:
    start, end = body_bounds(text)
    # Exclude third-party introductions, biographies and the second work in205.
    if identifier == 34901:
        start = text.index("ON LIBERTY.", start)
    elif identifier == 3420:
        start = text.index("INTRODUCTION.", text.index("A BRIEF SKETCH", start))
    elif identifier == 205:
        start = text.index("Economy", text.index("WALDEN", text.index("Contents", start)) + 6)
        # The second occurrence of the all-caps title starts the separate essay.
        matches = list(re.finditer(r"^ON THE DUTY OF CIVIL DISOBEDIENCE\s*$", text, re.M))
        if matches:
            end = matches[-1].start()
    elif identifier == 1342:
        # Austen main text begins after George Saintsbury's1894preface.
        start = text.index("It is a truth universally acknowledged", start)
    elif identifier == 59646:
        # Skip Elmgren's1864foreword/biography; select Wallin travel diary.
        anchor = re.search(r"^I\.\s*Afdelningen", text[start:end], re.M | re.I)
        if anchor:
            start += anchor.start()
        # The frozen fractions are sufficiently late to exclude front matter.
    return start, end


def build(download: bool = False) -> dict:
    contract = read_json(PILOT / "contract.json")
    license_path = PILOT / "sources" / "gutenberg-license.html"
    if download:
        license_path.write_bytes(fetch(LICENSE_URL))
        for name, url in RIGHTS_REFERENCES.items():
            (PILOT / "sources" / name).write_bytes(fetch(url))
    if not license_path.exists():
        raise ValueError("Missing archived rights policy; use --download")
    manifest = {"schema_version": "textlab-pilot-manifest-v1", "contract_sha256": sha256((PILOT / "contract.json").read_bytes()),
                "access_date": "2026-11-02", "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "rights_scope": "Catalog and embedded-license review; public-domain assertion in USA plus recorded author death >100 years before2026. Not a worldwide legal determination.",
                "rights_policy": {"url": LICENSE_URL, "path": str(license_path.relative_to(ROOT)).replace('\\', '/'), "sha256": sha256(license_path.read_bytes())},
                "label_inference": "Human authorship is inferred from attributed historical publication, not measured by a detector. Modern transcriptions may contain OCR/proofreading changes.", "sources": []}
    manifest["additional_rights_evidence"] = [{"url": url, "path": f"data/pilot/sources/{name}", "sha256": sha256((PILOT / "sources" / name).read_bytes())} for name, url in RIGHTS_REFERENCES.items()]
    rows = []
    for spec in contract["sources"]:
        identifier = spec["gutenberg_id"]
        raw_path = PILOT / "sources" / f"pg{identifier}.txt"
        page_path = raw_path.with_suffix(".html")
        raw_url = f"https://www.gutenberg.org/cache/epub/{identifier}/pg{identifier}.txt"
        page_url = f"https://www.gutenberg.org/ebooks/{identifier}"
        if download:
            raw_path.write_bytes(fetch(raw_url))
            page_path.write_bytes(fetch(page_url))
        raw, page = raw_path.read_bytes(), page_path.read_bytes()
        text = raw.decode("utf-8-sig")
        catalog = clean_html(page.decode("utf8"))
        if "Public domain in the USA." not in catalog:
            raise ValueError(f"Missing public-domain statement: {identifier}")
        people = catalog_contributors(page.decode("utf8"))
        if not any(person["role"] == "Author" and person["death_year"] == spec["author_death_year"] for person in people) or spec["author_death_year"] > 1925:
            raise ValueError(f"Missing/too recent author death evidence: {identifier}")
        if spec["publication_quote"] and spec["publication_quote"] not in normalize_excerpt(text):
            raise ValueError(f"Missing printed publication evidence: {identifier}")
        if "1.E." not in text or "Project Gutenberg" not in text:
            raise ValueError(f"Missing embedded Gutenberg license: {identifier}")
        a, b = author_body_bounds(identifier, text)
        excerpts = select_excerpts(text, a, b, minimum=180, maximum=300)
        entry = {**spec, "source_url": page_url, "raw_url": raw_url, "raw_path": str(raw_path.relative_to(ROOT)).replace('\\', '/'), "raw_sha256": sha256(raw),
                 "catalog_path": str(page_path.relative_to(ROOT)).replace('\\', '/'), "catalog_sha256": sha256(page), "access_date": "2026-11-02",
                 "encoding": "utf-8-sig", "offset_unit": "Unicode code points of raw decoded text; original LF/CRLF retained", "eligible_body_start": a, "eligible_body_end": b,
                 "rights_assertion": "Public domain in the USA.", "catalog_contributors": people, "excerpts": []}
        if spec.get("publication_evidence_url"):
            evidence_path = PILOT / "sources" / f"pg{identifier}-publication-evidence.bin"
            if download or not evidence_path.exists():
                evidence_path.write_bytes(fetch(spec["publication_evidence_url"]))
            entry["publication_evidence_path"] = str(evidence_path.relative_to(ROOT)).replace('\\', '/')
            entry["publication_evidence_sha256"] = sha256(evidence_path.read_bytes())
        for index, excerpt in enumerate(excerpts, 1):
            source_id = f"pg{identifier}-h{index}"
            row = {"source_id": source_id, "author_id": spec["author_id"], "document_id": f"pg{identifier}", "source_group_id": f"pg{identifier}",
                   "language": spec["language"], "genre": spec["genre"], "split": spec["split"], "label": "human", "model": None, "text": excerpt["text"],
                   "provenance": {"kind": "independent", "source": raw_url,
                                  "rights": {"status": "verified", "basis": "public-domain", "evidence": f"{page_url}; embedded license in {entry['raw_path']}; author died{spec['author_death_year']}; review scope and hashes in data/pilot/manifest.json"},
                                  "label": {"method": "verified-source", "evidence": f"Historical attributed publication{spec['publication_year']}, pre-LLM inference; manifest/source snapshots; code-point offsets[{excerpt['start']},{excerpt['end']})"}},
                   "excerpt": {key: excerpt[key] for key in ["start", "end", "fraction"]}, "text_sha256": sha256(excerpt["text"].encode())}
            entry["excerpts"].append({**excerpt, "source_id": source_id, "text_sha256": row["text_sha256"]})
            rows.append(row)
        manifest["sources"].append(entry)
    audit_groups(rows)
    manifest["human_count"] = len(rows)
    write_rows(PILOT / "human.jsonl", rows)
    manifest["human_jsonl_sha256"] = sha256((PILOT / "human.jsonl").read_bytes())
    write_json(PILOT / "manifest.json", manifest)
    combine()
    return manifest


def combine() -> list[dict]:
    rows = read_rows(PILOT / "human.jsonl")
    if (PILOT / "ai.jsonl").exists():
        rows += read_rows(PILOT / "ai.jsonl")
    audit_groups(rows)
    write_rows(PILOT / "corpus.jsonl", rows)
    return rows


def verify() -> dict:
    manifest = read_json(PILOT / "manifest.json")
    if sha256((PILOT / "contract.json").read_bytes()) != manifest["contract_sha256"]:
        raise ValueError("Contract hash changed after manifest build")
    if sha256((ROOT / manifest["rights_policy"]["path"]).read_bytes()) != manifest["rights_policy"]["sha256"]:
        raise ValueError("Rights policy SHA256 mismatch")
    for reference in manifest["additional_rights_evidence"]:
        if sha256((ROOT / reference["path"]).read_bytes()) != reference["sha256"]:
            raise ValueError("Additional rights evidence SHA256 mismatch")
    expected = {}
    for source in manifest["sources"]:
        raw = (ROOT / source["raw_path"]).read_bytes()
        verify_raw(source, raw)
        if sha256((ROOT / source["catalog_path"]).read_bytes()) != source["catalog_sha256"]:
            raise ValueError("Catalog SHA256 mismatch")
        if source.get("publication_evidence_path") and sha256((ROOT / source["publication_evidence_path"]).read_bytes()) != source["publication_evidence_sha256"]:
            raise ValueError("Publication evidence SHA256 mismatch")
        text = raw.decode(source["encoding"])
        for excerpt in source["excerpts"]:
            verify_excerpt(text, excerpt)
            expected[excerpt["source_id"]] = excerpt["text"]
    humans = read_rows(PILOT / "human.jsonl")
    if len(humans) != len(expected) or {row["source_id"]: row["text"] for row in humans} != expected:
        raise ValueError("Human records disagree with manifest excerpts")
    if sha256((PILOT / "human.jsonl").read_bytes()) != manifest["human_jsonl_sha256"]:
        raise ValueError("Human JSONL SHA256 mismatch")
    rows = read_rows(PILOT / "corpus.jsonl")
    ai_rows = read_rows(PILOT / "ai.jsonl") if (PILOT / "ai.jsonl").exists() else []
    if rows != humans + ai_rows:
        raise ValueError("Combined corpus differs from source JSONLs")
    contract = read_json(PILOT / "contract.json")
    sources = {f"pg{source['gutenberg_id']}": source for source in contract["sources"]}
    for row in ai_rows:
        log = read_json(ROOT / row["generation_log"])
        slug = row["model"].replace(":", "-").replace(".", "-")
        snapshot = read_json(PILOT / "logs" / f"model-{slug}.json")
        verify_generation(row, log, sources[row["source_group_id"]], contract, snapshot["tag"]["digest"])
    audit_groups(rows)
    return {"passed": True, "source_count": len(manifest["sources"]), "human_count": len(humans), "ai_count": len(ai_rows), "corpus_sha256": sha256((PILOT / "corpus.jsonl").read_bytes()), "scope": "hashes, extraction, metadata and split consistency only; rights/labels remain source-audit assertions"}


def ollama(path: str, payload: dict | None = None) -> dict:
    request = urllib.request.Request(OLLAMA + path, data=json.dumps(payload).encode() if payload is not None else None,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.load(response)


def generation_prompt(source: dict) -> str:
    if source["language"] == "sv":
        return f"Skriv en självständig sammanhängande svensk text på180–250ord i en litterär1800-talspräglad stil. Genre:{source['genre']}. Ämne:{source['topic']} Skriv endast själva texten, utan rubrik, förklaring eller punktlista. Citera inte eller återskapa något befintligt verk."
    return f"Write an original continuous English passage of180–250words in a nineteenth-century literary register. Genre:{source['genre']}. Topic:{source['topic']} Return only the passage, without a heading, explanation or bullet list. Do not quote or reconstruct any existing work."


def verify_generation(row: dict, log: dict, source: dict, contract: dict, model_digest: str) -> None:
    if log["model_digest"] != model_digest:
        raise ValueError("Generation model digest disagrees with installed-model snapshot")
    request = {"model": row["model"], "prompt": generation_prompt(source), "stream": False, "think": False, "options": contract["generation_options"]}
    if log["request"] != request or sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()) != log["request_sha256"]:
        raise ValueError("Generation request differs from frozen contract")
    if not log["response"].get("done"):
        raise ValueError("Incomplete generation log")
    raw_output = log["response"]["response"]
    if sha256(raw_output.encode()) != log["raw_response_field_sha256"]:
        raise ValueError("Generation raw response SHA256 mismatch")
    if raw_output.strip() != row["text"] or sha256(row["text"].encode()) != row["text_sha256"]:
        raise ValueError("AI output differs from actual generation log")
    expected = {"author_id": f"commission-pg{source['gutenberg_id']}", "document_id": f"generation-pg{source['gutenberg_id']}", "source_group_id": f"pg{source['gutenberg_id']}",
                "split": source["split"], "language": source["language"], "genre": source["genre"], "label": "ai"}
    if any(row[key] != value for key, value in expected.items()):
        raise ValueError("AI commissioning source-family metadata mismatch")


def generate(model: str | None = None) -> dict:
    """One actual recorded request per frozen source/model; no quality cherry-pick."""
    contract = read_json(PILOT / "contract.json")
    models = [model] if model else contract["models"]
    if any(value not in contract["models"] for value in models):
        raise ValueError("Model not in frozen contract")
    tags = ollama("/api/tags")
    version = ollama("/api/version")
    write_json(PILOT / "logs" / "ollama-runtime.json", {"version": version, "tags": tags, "captured_at": dt.datetime.now(dt.timezone.utc).isoformat()})
    known = {entry["name"]: entry for entry in tags["models"]}
    rows = read_rows(PILOT / "ai.jsonl") if (PILOT / "ai.jsonl").exists() else []
    ids = {row["source_id"] for row in rows}
    for model_name in models:
        if model_name not in known:
            raise ValueError(f"Required model is not installed:{model_name}; downloading is forbidden")
        slug = model_name.replace(":", "-").replace(".", "-")
        details = ollama("/api/show", {"model": model_name})
        write_json(PILOT / "logs" / f"model-{slug}.json", {"tag": known[model_name], "details": details})
        for source in contract["sources"]:
            identifier = source["gutenberg_id"]
            source_id = f"pg{identifier}-ai-{slug}"
            if source_id in ids:
                continue
            request = {"model": model_name, "prompt": generation_prompt(source), "stream": False, "think": False, "options": contract["generation_options"]}
            log_path = PILOT / "logs" / f"{source_id}.json"
            if log_path.exists():
                log = read_json(log_path)
                if log["request"] != request:
                    raise ValueError("Existing log has a different frozen request")
                response = log["response"]
            else:
                started = dt.datetime.now(dt.timezone.utc).isoformat()
                response = ollama("/api/generate", request)
                log = {"source_id": source_id, "commissioning_source_group_id": f"pg{identifier}", "model": model_name,
                       "model_digest": known[model_name]["digest"], "request": request,
                       "request_sha256": sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()),
                       "started_at": started, "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(), "response": response,
                       "raw_response_field_sha256": sha256(response.get("response", "").encode())}
                write_json(log_path, log)
            if not response.get("done") or not response.get("response", "").strip():
                raise ValueError(f"Empty/incomplete recorded generation:{source_id}")
            text = response["response"].strip()
            if len(text) > 10000:
                raise ValueError(f"Output exceeds evaluator capacity:{source_id}")
            row = {"source_id": source_id, "author_id": f"commission-pg{identifier}", "document_id": f"generation-pg{identifier}", "source_group_id": f"pg{identifier}", "commissioning_human_author_id": source["author_id"],
                   "related_source_id": f"pg{identifier}-h1", "language": source["language"], "genre": source["genre"], "split": source["split"], "label": "ai", "model": model_name,
                   "text": text, "text_sha256": sha256(text.encode()), "generation_log": str(log_path.relative_to(ROOT)).replace('\\', '/'),
                   "provenance": {"kind": "independent", "source": "Actual local Ollama generation; " + str(log_path.relative_to(ROOT)).replace('\\', '/'),
                                  "rights": {"status": "verified", "basis": "owned", "evidence": "Operator-commissioned original model output; no source passages in prompt; retained model license/details and actual logs in data/pilot/logs. Metadata ownership assertion, not a claim AI output is copyrightable."},
                                  "label": {"method": "generation-log", "evidence": f"{str(log_path.relative_to(ROOT)).replace(chr(92), '/')}; digest={known[model_name]['digest']}; request/output hashes retained"}}}
            rows.append(row)
            ids.add(source_id)
            write_rows(PILOT / "ai.jsonl", rows)
            combine()
            print(json.dumps({"generated": source_id, "words": len(text.split()), "done_reason": response.get("done_reason")}), flush=True)
    return verify()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "verify", "generate"])
    parser.add_argument("--download", action="store_true", help="Download sources, changing archived bytes and hashes")
    parser.add_argument("--model", choices=["llama3.2:3b", "qwen3.5:4b"])
    args = parser.parse_args()
    if args.command == "build":
        result = build(args.download)
        print(json.dumps({"human_count": result["human_count"], "sources": len(result["sources"])}))
    else:
        print(json.dumps(generate(args.model) if args.command == "generate" else verify()))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
