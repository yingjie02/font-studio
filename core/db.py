"""SQLite 状态管理：确认状态由文件所在文件夹决定"""
import sqlite3
import shutil
import tempfile
import zipfile
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS chars (
    char       TEXT PRIMARY KEY,
    png_path   TEXT,
    png_mtime  REAL,
    svg_path   TEXT,
    svg_mtime  REAL,
    in_font    INTEGER DEFAULT 0,
    font_mtime REAL,
    dy         INTEGER DEFAULT 0,
    dx         INTEGER DEFAULT 0,
    scale      REAL DEFAULT 1.0,
    confirmed  INTEGER DEFAULT 0,
    modified   INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS scans (
    path         TEXT PRIMARY KEY,
    mtime        REAL,
    n_chars      INTEGER,
    processed_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class DB:
    def __init__(self, path):
        self.path = Path(path)
        self.data_dir = self.path.parent
        self.confirmed_dir = self.data_dir / 'png_confirmed'
        self.unconfirmed_dir = self.data_dir / 'png_unconfirmed'
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self._ensure_dirs()
        self.sync_from_folders()
        self.conn.commit()

    def _migrate(self):
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(chars)")}
        if 'confirmed' not in cols:
            self.conn.execute("ALTER TABLE chars ADD COLUMN confirmed INTEGER DEFAULT 0")
        if 'modified' not in cols:
            self.conn.execute("ALTER TABLE chars ADD COLUMN modified INTEGER DEFAULT 0")
        self.conn.commit()

    def _ensure_dirs(self):
        self.confirmed_dir.mkdir(parents=True, exist_ok=True)
        self.unconfirmed_dir.mkdir(parents=True, exist_ok=True)

    def sync_from_folders(self):
        """扫描两个文件夹，重建/修正 DB 状态（非破坏性）"""
        if not self.confirmed_dir.exists() or not self.unconfirmed_dir.exists():
            return

        confirmed_chars = {}
        for png in self.confirmed_dir.glob('uni*.png'):
            try:
                char = chr(int(png.stem[3:], 16))
                confirmed_chars[char] = png
            except ValueError:
                continue

        unconfirmed_chars = {}
        for png in self.unconfirmed_dir.glob('uni*.png'):
            try:
                char = chr(int(png.stem[3:], 16))
                unconfirmed_chars[char] = png
            except ValueError:
                continue

        # 1. 重复：已确认优先，删未确认
        for char in list(confirmed_chars.keys() & unconfirmed_chars.keys()):
            png = unconfirmed_chars[char]
            try:
                png.unlink()
            except Exception:
                pass
            del unconfirmed_chars[char]

        # 2. DB 里 confirmed=1 但文件在 unconfirmed → 移到 confirmed
        to_move = []
        for char, png in list(unconfirmed_chars.items()):
            row = self.conn.execute(
                "SELECT confirmed FROM chars WHERE char=?", (char,)
            ).fetchone()
            if row and row['confirmed'] == 1:
                to_move.append((char, png))

        for char, png in to_move:
            target = self.confirmed_dir / png.name
            try:
                png.rename(target)
                confirmed_chars[char] = target
                del unconfirmed_chars[char]
            except Exception:
                pass

        # 3. 更新 DB：已确认
        for char, png in confirmed_chars.items():
            row = self.conn.execute(
                "SELECT char, confirmed, png_path FROM chars WHERE char=?", (char,)
            ).fetchone()
            if row:
                if row['confirmed'] != 1 or row['png_path'] != str(png):
                    self.conn.execute(
                        "UPDATE chars SET confirmed=1, png_path=?, "
                        "updated_at=CURRENT_TIMESTAMP WHERE char=?",
                        (str(png), char),
                    )
            else:
                self.conn.execute(
                    "INSERT INTO chars(char, png_path, confirmed) VALUES(?,?,1)",
                    (char, str(png)),
                )

        # 4. 更新 DB：未确认
        for char, png in unconfirmed_chars.items():
            row = self.conn.execute(
                "SELECT char, confirmed, png_path FROM chars WHERE char=?", (char,)
            ).fetchone()
            if row:
                if row['confirmed'] != 0 or row['png_path'] != str(png):
                    self.conn.execute(
                        "UPDATE chars SET confirmed=0, png_path=?, "
                        "updated_at=CURRENT_TIMESTAMP WHERE char=?",
                        (str(png), char),
                    )
            else:
                self.conn.execute(
                    "INSERT INTO chars(char, png_path, confirmed) VALUES(?,?,0)",
                    (char, str(png)),
                )

        # 5. DB 里有但两处都没文件 → 只清 png_path
        all_in_folders = set(confirmed_chars.keys()) | set(unconfirmed_chars.keys())
        for row in self.conn.execute("SELECT char, png_path FROM chars").fetchall():
            if row['char'] not in all_in_folders and row['png_path']:
                self.conn.execute(
                    "UPDATE chars SET png_path=NULL WHERE char=?", (row['char'],)
                )

        self.conn.commit()

    # ------- scans -------
    def scan_processed(self, path, mtime):
        row = self.conn.execute("SELECT mtime FROM scans WHERE path=?", (str(path),)).fetchone()
        return row is not None and abs(row['mtime'] - mtime) < 1.0

    def mark_scan(self, path, mtime, n):
        self.conn.execute(
            "INSERT OR REPLACE INTO scans(path, mtime, n_chars) VALUES(?,?,?)",
            (str(path), mtime, n),
        )
        self.conn.commit()

    # ------- chars CRUD -------
    def upsert_char(self, char, **fields):
        exists = self.conn.execute("SELECT char FROM chars WHERE char=?", (char,)).fetchone()
        if exists:
            if not fields:
                return
            keys = ','.join(f"{k}=?" for k in fields)
            self.conn.execute(
                f"UPDATE chars SET {keys}, updated_at=CURRENT_TIMESTAMP WHERE char=?",
                (*fields.values(), char),
            )
        else:
            cols = ','.join(['char'] + list(fields.keys()))
            ph = ','.join(['?'] * (len(fields) + 1))
            self.conn.execute(
                f"INSERT INTO chars({cols}) VALUES({ph})",
                (char, *fields.values()),
            )
        self.conn.commit()

    def get_char(self, char):
        return self.conn.execute("SELECT * FROM chars WHERE char=?", (char,)).fetchone()

    def all_chars(self):
        return self.conn.execute("SELECT * FROM chars ORDER BY char").fetchall()

    def get_png_path(self, char):
        row = self.get_char(char)
        if not row:
            return None
        if row['png_path'] and Path(row['png_path']).exists():
            return Path(row['png_path'])
        hex_code = f"{ord(char):04x}"
        for folder in (self.confirmed_dir, self.unconfirmed_dir, self.data_dir / 'png'):
            candidate = folder / f"uni{hex_code}.png"
            if candidate.exists():
                return candidate
        return None

    def filter_chars(self, status='all'):
        if status == 'confirmed':
            return self.conn.execute("SELECT * FROM chars WHERE confirmed=1 ORDER BY char").fetchall()
        elif status == 'unconfirmed':
            return self.conn.execute("SELECT * FROM chars WHERE confirmed=0 ORDER BY char").fetchall()
        elif status == 'modified':
            return self.conn.execute("SELECT * FROM chars WHERE modified=1 ORDER BY char").fetchall()
        elif status == 'adjusted':
            return self.conn.execute(
                "SELECT * FROM chars WHERE dy!=0 OR dx!=0 OR scale!=1.0 ORDER BY char"
            ).fetchall()
        else:
            return self.all_chars()

    def set_confirmed(self, char, confirmed=True):
        row = self.get_char(char)
        if not row:
            return False

        current_path = self.get_png_path(char)
        if not current_path or not current_path.exists():
            self.conn.execute(
                "UPDATE chars SET confirmed=?, updated_at=CURRENT_TIMESTAMP WHERE char=?",
                (1 if confirmed else 0, char),
            )
            self.conn.commit()
            return True

        target_dir = self.confirmed_dir if confirmed else self.unconfirmed_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / current_path.name

        try:
            if current_path != target_path:
                if target_path.exists():
                    current_path.unlink()
                else:
                    current_path.rename(target_path)
        except Exception as e:
            print(f"[warn] move {char} failed: {e}")
            return False

        self.conn.execute(
            "UPDATE chars SET confirmed=?, png_path=?, updated_at=CURRENT_TIMESTAMP WHERE char=?",
            (1 if confirmed else 0, str(target_path), char),
        )
        self.conn.commit()
        return True

    def batch_set_confirmed(self, chars, confirmed=True):
        if not chars:
            return 0
        n = 0
        for c in chars:
            if self.set_confirmed(c, confirmed):
                n += 1
        return n

    def set_modified(self, char, modified=True):
        self.conn.execute(
            "UPDATE chars SET modified=?, updated_at=CURRENT_TIMESTAMP WHERE char=?",
            (1 if modified else 0, char),
        )
        self.conn.commit()

    def delete_char(self, char):
        row = self.get_char(char)
        if not row:
            return False
        try:
            png = self.get_png_path(char)
            if png and png.exists():
                png.unlink()
            if row['svg_path'] and Path(row['svg_path']).exists():
                Path(row['svg_path']).unlink()
        except Exception as e:
            print(f"[warn] delete files failed: {e}")
        self.conn.execute("DELETE FROM chars WHERE char=?", (char,))
        self.conn.commit()
        return True

    
    def delete_all_unconfirmed(self):
        """删除所有未确认的字（含 PNG 和 SVG）"""
        rows = self.conn.execute(
            "SELECT char FROM chars WHERE confirmed=0"
        ).fetchall()
        n = 0
        for row in rows:
            if self.delete_char(row['char']):
                n += 1
        return n
    

    def stats(self):
        total = self.conn.execute("SELECT COUNT(*) FROM chars").fetchone()[0]
        in_font = self.conn.execute("SELECT COUNT(*) FROM chars WHERE in_font=1").fetchone()[0]
        confirmed = self.conn.execute("SELECT COUNT(*) FROM chars WHERE confirmed=1").fetchone()[0]
        modified = self.conn.execute("SELECT COUNT(*) FROM chars WHERE modified=1").fetchone()[0]
        adjusted = self.conn.execute(
            "SELECT COUNT(*) FROM chars WHERE dy!=0 OR dx!=0 OR scale!=1.0"
        ).fetchone()[0]
        return {
            'total': total,
            'in_font': in_font,
            'confirmed': confirmed,
            'unconfirmed': total - confirmed,
            'modified': modified,
            'adjusted': adjusted,
        }

    # ------- 备份 / 恢复 -------
    def backup(self, target_path, log=print):
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        n_conf = n_unconf = 0
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zf:
            for folder_name, folder_path in [
                ('png_confirmed', self.confirmed_dir),
                ('png_unconfirmed', self.unconfirmed_dir),
            ]:
                if not folder_path.exists():
                    continue
                for png in folder_path.glob('*.png'):
                    zf.write(png, f"{folder_name}/{png.name}")
                    if folder_name == 'png_confirmed':
                        n_conf += 1
                    else:
                        n_unconf += 1
            if self.path.exists():
                zf.write(self.path, 'project.db')
        size_mb = target.stat().st_size / 1024 / 1024
        log(f"备份完成：已确认 {n_conf}，未确认 {n_unconf}，{size_mb:.1f}MB → {target}")
        return target

    def restore(self, backup_path, log=print):
        backup_path = Path(backup_path)
        if not backup_path.exists():
            return False, "备份文件不存在"

        self.confirmed_dir.mkdir(parents=True, exist_ok=True)
        self.unconfirmed_dir.mkdir(parents=True, exist_ok=True)

        n_conf = n_unconf = n_skip = 0

        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            with zipfile.ZipFile(backup_path, 'r') as zf:
                zf.extractall(tmp)

            # 1. 先恢复已确认
            src_conf = tmp / 'png_confirmed'
            if src_conf.exists():
                for png in src_conf.glob('uni*.png'):
                    dest = self.confirmed_dir / png.name
                    if dest.exists():
                        n_skip += 1
                        continue
                    try:
                        shutil.copy2(png, dest)
                        n_conf += 1
                    except Exception as e:
                        log(f"[warn] copy confirmed {png.name} failed: {e}")

            # 2. 再恢复未确认，跳过已确认已有的
            src_unconf = tmp / 'png_unconfirmed'
            if src_unconf.exists():
                for png in src_unconf.glob('uni*.png'):
                    if (self.confirmed_dir / png.name).exists():
                        n_skip += 1
                        continue
                    dest = self.unconfirmed_dir / png.name
                    if dest.exists():
                        n_skip += 1
                        continue
                    try:
                        shutil.copy2(png, dest)
                        n_unconf += 1
                    except Exception as e:
                        log(f"[warn] copy unconfirmed {png.name} failed: {e}")

            # 3. 合并 DB 参数
            src_db = tmp / 'project.db'
            if src_db.exists():
                try:
                    src_conn = sqlite3.connect(str(src_db))
                    src_conn.row_factory = sqlite3.Row
                    for row in src_conn.execute("SELECT * FROM chars"):
                        char = row['char']
                        existing = self.get_char(char)
                        if existing:
                            self.conn.execute(
                                "UPDATE chars SET dy=?, dx=?, scale=?, modified=?, "
                                "updated_at=CURRENT_TIMESTAMP WHERE char=?",
                                (row['dy'] or 0, row['dx'] or 0, row['scale'] or 1.0,
                                 row['modified'] or 0, char)
                            )
                    src_conn.close()
                except Exception as e:
                    log(f"[warn] DB merge failed: {e}")

        self.sync_from_folders()

        msg = f"恢复完成：已确认 {n_conf}，未确认 {n_unconf}，跳过 {n_skip}"
        log(msg)
        return True, msg