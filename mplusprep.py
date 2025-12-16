import os, sys, re, argparse, pyreadstat
import pandas as pd

def read_csv_with_fallback(p):
    for e in ["utf-8", "gbk", "gb2312", "cp936", "latin1"]:
        try:
            return pd.read_csv(p, encoding=e), e
        except UnicodeDecodeError:
            pass
    if input("\n⚠️  CSV 文件编码无法自动识别\n是否由 mplusprep 强制修复（latin1）？ [y/N]: ").lower() == "y":
        return pd.read_csv(p, encoding="latin1"), "latin1"
    raise UnicodeDecodeError("csv", b"", 0, 1, "用户拒绝自动修复")

def read_data(p):
    ext = os.path.splitext(p)[1].lower()
    if ext == ".csv":
        return read_csv_with_fallback(p)[0]
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(p)
    if ext == ".sav":
        return pyreadstat.read_sav(p, apply_value_formats=False, formats_as_category=False)[0]
    raise ValueError(f"不支持的文件格式: {ext}")

def illegal_names(cols):
    return [c for c in cols if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", c) or len(c) > 8]

def sanitize_names(cols):
    mp, used, counter = {}, set(), 1
    for c in cols:
        n = re.sub(r"[^A-Za-z0-9_]", "", c)
        if not n or n[0].isdigit():
            n = f"v{counter}"
        n = n[:8]
        while n in used:
            n = n[:7] + str(counter % 10)
        mp[c] = n
        used.add(n)
        counter += 1
    return mp

def write_dat(df, path):
    df.to_csv(path, sep=" ", index=False, header=False, float_format="%.6f")

def fmt_names(names, per_line=5, indent="    "):
    lines = [" ".join(names[i:i + per_line]) for i in range(0, len(names), per_line)]
    return "\n".join(indent + l for l in lines)

def write_inp_med(df, out, dat_abs):
    X, M, Y = df.columns[:3]
    with open(out, "w", encoding="utf-8") as f:
        f.write("TITLE: Simple mediation model (X M Y);\n\n")
        f.write("DATA:\n"); f.write(f"  FILE = {dat_abs};\n\n")
        f.write("VARIABLE:\n  NAMES =\n"); f.write(fmt_names(df.columns)); f.write(";\n\n")
        f.write(f"  USEVARIABLES = {X} {M} {Y};\n\n")
        f.write("ANALYSIS:\n  ESTIMATOR = MLR;\n  BOOTSTRAP = 5000;\n\n")
        f.write("MODEL:\n"); f.write(f"  {M} ON {X} (a);\n"); f.write(f"  {Y} ON {M} (b);\n"); f.write(f"  {Y} ON {X} (c);\n\n")
        f.write("MODEL CONSTRAINT:\n  NEW(DIRECT INDIRECT TOTAL);\n  INDIRECT = a*b;\n  DIRECT = c;\n  TOTAL = DIRECT + INDIRECT;\n\n")
        f.write("OUTPUT:\n  STANDARDIZED CINTERVAL(BOOTSTRAP);\n")

def write_inp_mod(df, out, dat_abs):
    X, M, Y, W = df.columns[:4]
    with open(out, "w", encoding="utf-8") as f:
        f.write("TITLE: Moderated mediation model;\n\n")
        f.write("DATA:\n"); f.write(f"  FILE = {dat_abs};\n\n")
        f.write("VARIABLE:\n  NAMES =\n"); f.write(fmt_names(df.columns)); f.write(";\n\n")
        f.write(f"  USEVARIABLES = {X} {M} {Y} {W} XW;\n\n")
        f.write("DEFINE:\n"); f.write(f"  XW = {X}*{W};\n\n")
        f.write("ANALYSIS:\n  ESTIMATOR = MLR;\n  BOOTSTRAP = 5000;\n\n")
        f.write("MODEL:\n"); f.write(f"  {M} ON {X} (a1) {W} (a2) XW (a3);\n"); f.write(f"  {Y} ON {M} (b) {X};\n\n")
        f.write("MODEL CONSTRAINT:\n  NEW(INDIRECT);\n  INDIRECT = (a1 + a3*0)*b;\n\n")
        f.write("OUTPUT:\n  STANDARDIZED CINTERVAL(BOOTSTRAP);\n")

def convert(inp, prefix, mode):
    df = read_data(inp)
    mp = None
    bad = illegal_names(df.columns)
    if bad:
        print("\n⚠️  检测到 Mplus 非法变量名：")
        for v in bad:
            print(f"  - {v}")
        if input("是否由 mplusprep 自动修复变量名？ [y/N]: ").lower() != "y":
            raise ValueError("用户拒绝自动修复变量名")
        mp = sanitize_names(df.columns)
        df = df.rename(columns=mp)
        print("\n✔ 变量名映射：")
        for k, v in mp.items():
            if k != v:
                print(f"  {k} → {v}")
    dat = prefix + ".dat"
    inp_file = prefix + ".inp"
    write_dat(df, dat)
    dat_abs = os.path.abspath(dat)
    (write_inp_mod if mode == "w" else write_inp_med)(df, inp_file, dat_abs)
    if mp:
        map_file = prefix + "_variable_map.csv"
        pd.DataFrame(list(mp.items()), columns=["original", "mplus"]).to_csv(map_file, index=False, encoding="utf-8-sig")
        print(f"\n📄 变量映射表已输出: {os.path.abspath(map_file)}")
    print("\n✅ 转换完成")
    print(dat_abs)
    print(os.path.abspath(inp_file))

def main():
    p = argparse.ArgumentParser(prog="mplusprep", description="Prepare Mplus mediation / moderated mediation models")
    p.add_argument("input", help="csv / xlsx / sav 数据文件")
    p.add_argument("-m", action="store_true", help="简单中介模型（默认）")
    p.add_argument("-w", action="store_true", help="调节的中介模型")
    p.add_argument("-o", help="输出文件前缀")
    args = p.parse_args()
    if args.m and args.w:
        raise ValueError("不能同时使用 -m 和 -w")
    mode = "w" if args.w else "m"
    infile = args.input.lstrip("-")
    if not os.path.exists(infile):
        raise FileNotFoundError(f"找不到文件: {infile}")
    prefix = args.o if args.o else os.path.splitext(os.path.basename(infile))[0]
    convert(infile, prefix, mode)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 错误: {e}\n")
        argparse.ArgumentParser().print_help()
        sys.exit(1)
