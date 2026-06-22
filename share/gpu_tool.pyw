# -*- coding: utf-8 -*-
"""
3DMark 스크립트 런처 (GUI)

- 더블클릭으로 실행되며 콘솔(cmd) 창이 뜨지 않습니다(pythonw / .pyw).
- 내부 스크립트도 창 없이 백그라운드로 실행됩니다(CREATE_NO_WINDOW).
- 가로 3칸(수집 / 관리 / HTML) + 하단 상태창.
"""
import os
import re
import sys
import json
import queue
import datetime
import threading
import subprocess
from pathlib import Path

import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
WEB = ROOT / "web"
CACHE = SCRIPTS / "_gpu_id_catalog_full.json"
CATALOG_PY = SCRIPTS / "gpu_catalog.py"

# 콘솔 없는 pythonw 로 떠 있어도 자식 스크립트는 python.exe 로 실행(출력 캡처용)
PYEXE = sys.executable
if PYEXE.lower().endswith("pythonw.exe"):
    _c = PYEXE[:-len("pythonw.exe")] + "python.exe"
    if os.path.exists(_c):
        PYEXE = _c
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

BENCHES = [("timespy", "Time Spy"), ("firestrike", "Fire Strike"),
           ("portroyal", "Port Royal"), ("steelnomad", "Steel Nomad DX12")]
DISP2KEY = {d: k for k, d in BENCHES}

# 시리즈 목록(추가용) — gpu_catalog 에서 한 번만 읽음(시리즈는 거의 안 바뀜)
sys.path.insert(0, str(SCRIPTS))
try:
    import gpu_catalog as _cat
    SERIES = {"desktop": list(_cat.DESKTOP_CATALOG), "laptop": list(_cat.LAPTOP_CATALOG)}
except Exception:
    SERIES = {"desktop": [], "laptop": []}


def add_to_catalog(kind, series, name, gid):
    """gpu_catalog.py 에 모델을 추가/갱신한다. 중복 판단 기준은 gpuId.
      - 같은 id 가 이미 있으면: 이름만 새 이름으로 교체(덮어쓰기) → ('renamed', 기존이름)
      - 없으면: 선택 시리즈 dict 맨 앞에 추가 → ('added', None)
    """
    text = CATALOG_PY.read_text(encoding="utf-8")
    var = "DESKTOP_CATALOG" if kind == "desktop" else "LAPTOP_CATALOG"
    start = text.find(var)
    if start < 0:
        raise ValueError("카탈로그를 찾을 수 없습니다")
    end = text.find("LAPTOP_CATALOG") if kind == "desktop" else text.find("def iter_models")
    if end < 0:
        end = len(text)
    block = text[start:end]

    # 1) 같은 id 가 이미 있나? (이름 무관) → 이름만 교체
    mm = re.search(r'"([^"]+)"(\s*:\s*)%d(\s*,)' % gid, block)
    if mm:
        oldname = mm.group(1)
        if oldname == name:
            raise ValueError("이미 있습니다 (id=%d, '%s')" % (gid, name))
        new = '"%s"%s%d%s' % (name, mm.group(2), gid, mm.group(3))
        block2 = block[:mm.start()] + new + block[mm.end():]
        CATALOG_PY.write_text(text[:start] + block2 + text[end:], encoding="utf-8")
        return ("renamed", oldname)

    # 2) 새 id → 시리즈에 추가
    key = '"%s": {' % series
    ki = block.find(key)
    if ki >= 0:                          # (a) 기존 시리즈에 추가
        close = block.find("    },", ki)
        seg = block[ki: close if close > 0 else len(block)]
        if ('"%s":' % name) in seg:
            raise ValueError("같은 시리즈에 '%s' 이름이 이미 있습니다" % name)
        at = start + ki + len(key)
        text = text[:at] + ('\n        "%s": %d,' % (name, gid)) + text[at:]
        CATALOG_PY.write_text(text, encoding="utf-8")
        return ("added", None)
    # (b) 신규 시리즈 생성 — 카탈로그 dict 끝에 새 시리즈 dict 추가
    if not series:
        raise ValueError("시리즈를 입력/선택하세요")
    ci = block.rfind("\n}")              # 카탈로그 dict 의 닫는 '}'
    if ci < 0:
        raise ValueError("카탈로그 구조를 해석할 수 없습니다")
    pos = start + ci + 1
    new_series = '    "%s": {\n        "%s": %d,\n    },\n' % (series, name, gid)
    text = text[:pos] + new_series + text[pos:]
    CATALOG_PY.write_text(text, encoding="utf-8")
    return ("added_series", series)


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.busy = False
        self.found_id = None
        self.found_name = ""
        self.find_results = []
        self.action_btns = []
        self.proc = None          # 실행 중인 수집 프로세스
        self.scraping = False     # 수집 작업 진행 중 여부
        self.stopped = False      # 사용자가 중지했는지
        root.title("3DMark 도구")
        root.geometry("880x470")
        root.minsize(820, 440)
        self._build()
        self.kind.trace_add("write", self.refresh_collect_time)
        self.bench.trace_add("write", self.refresh_collect_time)
        self.refresh_times()
        root.after(80, self._drain)

    # ------------------------------ UI ------------------------------
    def _build(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        self.status = ttk.Label(outer, text="대기 중", relief="sunken", anchor="w", padding=(8, 6))
        self.status.pack(side="bottom", fill="x", pady=(10, 0))
        cols = ttk.Frame(outer)
        cols.pack(side="top", fill="both", expand=True)
        for c in range(3):
            cols.columnconfigure(c, weight=1, uniform="col")
        cols.rowconfigure(0, weight=1)
        self._build_collect(cols)
        self._build_manage(cols)
        self._build_html(cols)

    def _build_collect(self, parent):
        f = ttk.LabelFrame(parent, text="수집", padding=10)
        f.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Label(f, text="방식").pack(anchor="w")
        self.mode = tk.StringVar(value="update")
        ttk.Radiobutton(f, text="전체 수집", variable=self.mode, value="full").pack(anchor="w")
        ttk.Radiobutton(f, text="업데이트", variable=self.mode, value="update").pack(anchor="w")
        ttk.Separator(f).pack(fill="x", pady=7)
        ttk.Label(f, text="대상").pack(anchor="w")
        self.kind = tk.StringVar(value="desktop")
        ttk.Radiobutton(f, text="데스크탑", variable=self.kind, value="desktop").pack(anchor="w")
        ttk.Radiobutton(f, text="노트북", variable=self.kind, value="laptop").pack(anchor="w")
        ttk.Separator(f).pack(fill="x", pady=7)
        ttk.Label(f, text="벤치마크").pack(anchor="w")
        self.bench = tk.StringVar(value=BENCHES[0][1])
        ttk.Combobox(f, textvariable=self.bench, values=[d for _, d in BENCHES],
                     state="readonly").pack(fill="x", pady=(2, 0))
        self.lbl_collect = ttk.Label(f, text="", foreground="#888888")
        self.lbl_collect.pack(anchor="w", pady=(5, 0))
        br = ttk.Frame(f); br.pack(fill="x", side="bottom")
        self.scrape_btn = ttk.Button(br, text="수집", command=self.on_scrape)
        self.scrape_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.stop_btn = ttk.Button(br, text="중지", command=self.on_stop, state="disabled")
        self.stop_btn.pack(side="left")
        self.action_btns.append(self.scrape_btn)

    def _build_manage(self, parent):
        f = ttk.LabelFrame(parent, text="관리", padding=10)
        f.grid(row=0, column=1, sticky="nsew", padx=6)
        top = ttk.Frame(f); top.pack(fill="x")
        b1 = ttk.Button(top, text="GPU ID 스캔", command=self.on_rescan)
        b1.pack(side="left", expand=True, fill="x", padx=(0, 3))
        b2 = ttk.Button(top, text="무결성 검사", command=self.on_verify)
        b2.pack(side="left", expand=True, fill="x", padx=(3, 0))
        self.action_btns += [b1, b2]
        ttk.Separator(f).pack(fill="x", pady=7)
        sr = ttk.Frame(f); sr.pack(fill="x")
        ttk.Label(sr, text="모델명").pack(side="left")
        self.find_entry = ttk.Entry(sr)
        self.find_entry.pack(side="left", expand=True, fill="x", padx=4)
        self.find_entry.bind("<Return>", lambda e: self.on_find())
        bf = ttk.Button(sr, text="찾기", command=self.on_find)
        bf.pack(side="left")
        self.action_btns.append(bf)
        self.find_list = tk.Listbox(f, height=4)
        self.find_list.pack(fill="x", pady=5)
        self.find_list.bind("<<ListboxSelect>>", self.on_pick)
        nr = ttk.Frame(f); nr.pack(fill="x")
        ttk.Label(nr, text="표시이름").pack(side="left")
        self.add_name = ttk.Entry(nr)
        self.add_name.pack(side="left", expand=True, fill="x", padx=4)
        self.add_name.bind("<KeyRelease>", lambda e: self._preview())
        kr = ttk.Frame(f); kr.pack(fill="x", pady=(5, 0))
        self.add_kind = tk.StringVar(value="desktop")
        ttk.Radiobutton(kr, text="데스크탑", variable=self.add_kind, value="desktop",
                        command=self._refresh_series).pack(side="left")
        ttk.Radiobutton(kr, text="노트북", variable=self.add_kind, value="laptop",
                        command=self._refresh_series).pack(side="left")
        sr2 = ttk.Frame(f); sr2.pack(fill="x", pady=(5, 0))
        ttk.Label(sr2, text="시리즈").pack(side="left")
        self.add_series = ttk.Combobox(sr2, values=SERIES["desktop"])   # 편집 가능: 기존 선택 + 신규 직접 입력
        self.add_series.pack(side="left", expand=True, fill="x", padx=4)
        self.preview = ttk.Label(f, text="", foreground="#2563eb")
        self.preview.pack(anchor="w", pady=(6, 0))
        ba = ttk.Button(f, text="추가", command=self.on_add)
        ba.pack(fill="x", pady=(4, 0))
        self.action_btns.append(ba)

    def _build_html(self, parent):
        f = ttk.LabelFrame(parent, text="HTML", padding=10)
        f.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        bb = ttk.Button(f, text="차트 업데이트", command=self.on_build)
        bb.pack(fill="x", pady=(5, 0))
        self.lbl_update = ttk.Label(f, text="", foreground="#888888")
        self.lbl_update.pack(anchor="w", pady=(2, 10))
        bs = ttk.Button(f, text="공유 파일 생성", command=self.on_share)
        bs.pack(fill="x")
        self.lbl_share = ttk.Label(f, text="", foreground="#888888")
        self.lbl_share.pack(anchor="w", pady=(2, 10))
        bf = ttk.Button(f, text="폴더 열기", command=self.on_folder)
        bf.pack(fill="x")
        self.action_btns += [bb, bs]

    # ------------------------- 상태 / 스레드 -------------------------
    def _drain(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "status":
                    self.status.config(text=val)
                elif kind == "busy":
                    self._set_busy(val)
                    if not val:
                        self.refresh_times()
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    def _set_busy(self, b):
        self.busy = b
        for btn in self.action_btns:
            btn.config(state="disabled" if b else "normal")
        self.stop_btn.config(state="normal" if (b and self.scraping) else "disabled")

    def set_status(self, t):
        self.q.put(("status", t))

    # ----------------------- 최근 시각 표시 -----------------------
    @staticmethod
    def _fmt(ts):
        return datetime.datetime.fromtimestamp(ts).strftime("%Y.%m.%d %H:%M:%S")

    def refresh_collect_time(self, *_args):
        kind = self.kind.get()
        bench = DISP2KEY.get(self.bench.get(), "timespy")
        d = ROOT / "output" / kind / bench
        files = list(d.glob("3dmark_*_scores_*.xlsx")) if d.exists() else []
        if not files:
            self.lbl_collect.config(text="최근 수집: 없음")
            return
        latest = max(files, key=lambda p: p.stat().st_mtime)
        m = re.search(r"_(\d{8})_(\d{6})", latest.name)   # 파일명의 수집 시각
        if m:
            g1, g2 = m.group(1), m.group(2)
            dt = "%s.%s.%s %s:%s:%s" % (g1[:4], g1[4:6], g1[6:8], g2[:2], g2[2:4], g2[4:6])
        else:
            dt = self._fmt(latest.stat().st_mtime)
        self.lbl_collect.config(text="최근 수집: " + dt)

    def refresh_share_time(self):
        files = list(WEB.glob("3DMark_*_share.html")) if WEB.exists() else []
        if files:
            latest = max(files, key=lambda p: p.stat().st_mtime)
            self.lbl_share.config(text="최근 공유: " + self._fmt(latest.stat().st_mtime))
        else:
            self.lbl_share.config(text="최근 공유: 없음")

    def refresh_update_time(self):
        f = WEB / "chart_data.js"
        if f.exists():
            self.lbl_update.config(text="최근 업데이트: " + self._fmt(f.stat().st_mtime))
        else:
            self.lbl_update.config(text="최근 업데이트: 없음")

    def refresh_times(self):
        self.refresh_collect_time()
        self.refresh_share_time()
        self.refresh_update_time()

    def _start(self, target):
        if self.busy:
            return
        self.q.put(("busy", True))
        threading.Thread(target=target, daemon=True).start()

    def _popen(self, args):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.Popen(
            args, cwd=str(SCRIPTS), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, creationflags=NO_WINDOW, text=True, encoding="utf-8",
            errors="replace", bufsize=1)

    # ------------------------------ 수집 ------------------------------
    def on_scrape(self):
        if self.busy:
            return
        kind = self.kind.get()
        bench = DISP2KEY.get(self.bench.get(), "timespy")
        mode = self.mode.get()
        self.scraping = True
        self.stopped = False
        self._start(lambda: self._scrape(kind, bench, mode))

    def on_stop(self):
        p = self.proc
        if not (self.scraping and p and p.poll() is None):
            return
        self.stopped = True
        self.set_status("수집 중지 중...")
        try:    # 자식(브라우저 포함) 프로세스 트리까지 종료
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           creationflags=NO_WINDOW, capture_output=True)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass

    def _scrape(self, kind, bench, mode):
        args = [PYEXE, str(SCRIPTS / "scrape.py"), "--kind", kind, "--bench", bench,
                "--full" if mode == "full" else "--update"]
        prog = re.compile(r"\[(\d+)/(\d+)\]")
        warn = re.compile(r"gpuId=(\d+): 오류 ([^:]+):")   # 실패 사유(예외 종류)
        total = done = skipped = 0
        with_data = None
        failed = []          # [(모델명, 사유), ...]
        warns = {}           # gpuId -> 사유
        blocked = False
        try:
            proc = self._popen(args)
        except Exception as e:
            self.set_status("실행 오류: %s" % e)
            self.scraping = False
            self.q.put(("busy", False))
            return
        self.proc = proc
        for line in proc.stdout:
            wm = warn.search(line)
            if wm:
                warns[wm.group(1)] = wm.group(2).strip()
            m = prog.search(line)
            if m:
                done, total = int(m.group(1)), int(m.group(2))
                if "미등록" in line:
                    skipped += 1
                elif "평균=None" in line and "결과수=None" in line:
                    idm = re.search(r"\(id=(\d+)\)", line)
                    reason = warns.get(idm.group(1), "응답 없음") if idm else "응답 없음"
                    failed.append((self._model(line) or "?", reason))
                self.set_status("수집 중...  %d개 중 %d개" % (total, done))
            sm = re.search(r"점수 확보 (\d+)개", line)
            if sm:
                with_data = int(sm.group(1))
            if "차단" in line:
                blocked = True
        proc.wait()
        self.proc = None
        self.scraping = False
        if self.stopped:
            msg = "수집 중지됨  (%d/%d 처리)" % (done, total)
        elif blocked:
            msg = "차단되어 중단됨  (%d/%d 처리)" % (done, total)
        else:
            collected = max(0, total - len(failed) - skipped)
            msg = "%d개 중 %d개 수집 완료" % (total, collected)
            if with_data is not None:
                msg += ", %d개 데이터 존재" % with_data
            if failed:
                parts = ", ".join("%s: %s" % (nm, rs) for nm, rs in failed[:8])
                if len(failed) > 8:
                    parts += " ..."
                msg += ", %d개 수집 실패 (%s)" % (len(failed), parts)
        self.set_status(msg)
        self.q.put(("busy", False))

    @staticmethod
    def _model(line):
        m = re.search(r"\]\s*(.+?)\s*\(id=", line)
        if not m:
            return None
        return m.group(1).split(" / ")[-1].strip()

    # ------------------------------ 관리 ------------------------------
    def on_rescan(self):
        self._start(lambda: self._simple(
            [PYEXE, str(SCRIPTS / "collect_gpu_ids.py"), "--rescan"],
            "GPU ID 스캔 중...  (수 분 소요)", "GPU ID 스캔 완료",
            re.compile(r"(\d+)개 GPU 저장"), "", "개 저장"))

    def on_verify(self):
        self._start(lambda: self._simple(
            [PYEXE, str(SCRIPTS / "collect_gpu_ids.py"), "--verify"],
            "무결성 검사 중...", "무결성 검사 완료",
            re.compile(r"주의 항목 (\d+)건"), "주의 ", "건"))

    def _simple(self, args, busy_msg, done_msg, rgx=None, pre="", suf=""):
        self.set_status(busy_msg)
        extra = None
        try:
            proc = self._popen(args)
        except Exception as e:
            self.set_status("실행 오류: %s" % e)
            self.q.put(("busy", False))
            return
        last = ""
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                last = line
            if rgx:
                m = rgx.search(line)
                if m:
                    extra = m.group(1)
        proc.wait()
        if proc.returncode == 0:
            msg = done_msg
            if extra is not None:
                msg += "  (%s%s%s)" % (pre, extra, suf)
            self.set_status(msg)
        else:
            self.set_status("오류 (코드 %d): %s" % (proc.returncode, last[:70]))
        self.q.put(("busy", False))

    def on_find(self):
        if self.busy:
            return
        term = self.find_entry.get().strip()
        self.find_list.delete(0, "end")
        self.find_results = []
        self.found_id = None
        self._preview()
        if not term:
            return
        if not CACHE.exists():
            self.set_status("캐시 없음 — 먼저 'GPU ID 스캔'을 실행하세요")
            return
        try:
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception as e:
            self.set_status("캐시 읽기 오류: %s" % e)
            return
        tl = term.lower()
        hits = sorted(((int(i), n) for i, n in cache.items() if tl in n.lower()),
                      key=lambda x: x[1])
        if not hits:
            self.set_status("'%s' 검색 결과 없음" % term)
            return
        self.find_results = hits
        for i, n in hits:
            self.find_list.insert("end", "%-5d  %s" % (i, n))
        self.set_status("%d건 찾음 — 목록에서 선택하세요" % len(hits))

    @staticmethod
    def _suggest_name(raw):
        """3DMark 등록명에서 제조사/패밀리 접두어를 떼어 짧은 표시이름 제안.
        (예: 'AMD Radeon RX 7400' → '7400', 'NVIDIA GeForce RTX 5070' → '5070')
        VRAM(8G 등) 은 등록명에 없으므로 사용자가 직접 붙인다."""
        s = (raw or "").strip()
        prefixes = ("NVIDIA ", "AMD ", "Intel ", "GeForce ", "Radeon ",
                    "RX ", "RTX ", "GTX ", "Arc ")
        changed = True
        while changed:
            changed = False
            for p in prefixes:
                if s.startswith(p):
                    s = s[len(p):]
                    changed = True
        return s.strip() or raw

    def on_pick(self, _e=None):
        sel = self.find_list.curselection()
        if not sel:
            return
        i, n = self.find_results[sel[0]]
        self.found_id = i
        self.found_name = n
        self.add_name.delete(0, "end")
        self.add_name.insert(0, self._suggest_name(n))   # raw 이름 대신 짧은 제안
        self._apply_series_suggestion()                  # 이름 기반 시리즈 자동 추천
        self._preview()
        self.set_status("선택: %s (id=%d) — 표시이름/시리즈 확인 후 [추가]" % (n, i))

    def _preview(self):
        if self.found_id is None:
            self.preview.config(text="")
        else:
            self.preview.config(text='"%s": %d' % (self.add_name.get().strip(), self.found_id))

    @staticmethod
    def _guess_series(raw):
        """3DMark 등록명 → 기존 시리즈 후보 추정(없으면 '')."""
        s = (raw or "").lower()
        m = re.search(r"arc\s*([ab])\s*\d{3}", s)        # Arc A380 / B580
        if m:
            return "Arc " + m.group(1).upper()
        m = re.search(r"(rtx|gtx)\s*(\d{4})", s)          # RTX 5070 / GTX 1660
        if m:
            return ("RTX " if m.group(1) == "rtx" else "GTX ") + m.group(2)[:2]
        if "titan" in s or re.search(r"\bgt\s*10[0-9]0", s):
            return "GTX 10"
        if "radeon vii" in s or re.search(r"vega\s*(56|64)", s):
            return "RX VEGA"
        m = re.search(r"rx\s*(\d{3,4})", s)               # RX 7400 / RX 580
        if m:
            n = m.group(1)
            return "RX " + (n[0] + "000" if len(n) == 4 else "500")
        return ""

    def _apply_series_suggestion(self):
        avail = SERIES.get(self.add_kind.get(), [])
        self.add_series.config(values=avail)
        g = self._guess_series(self.found_name) if self.found_name else ""
        self.add_series.set(g if g in avail else "")     # 기존 시리즈일 때만 자동 채움

    def _refresh_series(self):
        self._apply_series_suggestion()

    def on_add(self):
        if self.busy:
            return
        name = self.add_name.get().strip()
        series = self.add_series.get().strip()
        if self.found_id is None:
            self.set_status("먼저 '찾기' 후 목록에서 GPU 를 선택하세요")
            return
        if not name:
            self.set_status("표시이름을 입력하세요")
            return
        try:    # 시리즈는 '신규 추가'일 때만 필요(이름 교체는 기존 위치 유지)
            result, old = add_to_catalog(self.add_kind.get(), series, name, self.found_id)
        except Exception as e:
            self.set_status("추가 실패: %s" % e)
            return
        if result == "renamed":
            self.set_status('이름 변경: "%s" → "%s"  (id=%d) · 차트 업데이트 후 반영'
                            % (old, name, self.found_id))
        elif result == "added_series":
            k = self.add_kind.get()
            if series not in SERIES[k]:
                SERIES[k].append(series)
            self.add_series.config(values=SERIES[k])     # 새 시리즈를 목록에도 반영
            self.set_status('새 시리즈 "%s" 생성 + "%s": %d 추가 (%s)'
                            % (series, name, self.found_id, k))
        else:
            self.set_status('추가 완료: "%s": %d  →  %s / %s'
                            % (name, self.found_id, self.add_kind.get(), series))

    # ------------------------------ HTML ------------------------------
    def on_share(self):
        self._start(lambda: self._simple(
            [PYEXE, str(SCRIPTS / "make_share.py")],
            "공유 파일 생성 중...", "공유 파일 생성 완료"))

    def on_build(self):
        self._start(lambda: self._simple(
            [PYEXE, str(SCRIPTS / "build_chart_data.py")],
            "차트 데이터 갱신 중...", "차트 업데이트 완료"))

    def on_folder(self):
        try:
            os.startfile(str(WEB))   # Windows 탐색기로 web 폴더 열기
        except Exception as e:
            self.set_status("폴더 열기 실패: %s" % e)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
