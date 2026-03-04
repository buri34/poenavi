"""PoEクライアントのTCP接続を強制切断してログアウトする（Windows専用）"""

import sys


def disconnect_poe() -> tuple:
    """PoEのTCP接続を強制切断する。戻り値: (成功bool, メッセージstr)"""
    if sys.platform != "win32":
        return (False, "Windows専用機能です")

    import ctypes
    import ctypes.wintypes as wt

    # --- 管理者権限チェック ---
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = False
    if not is_admin:
        return (False, "管理者権限が必要です。PoENaviを「管理者として実行」してください。")

    # --- 定数 ---
    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    TCP_TABLE_OWNER_PID_ALL = 5
    AF_INET = 2
    MIB_TCP_STATE_DELETE_TCB = 12
    NO_ERROR = 0

    # --- プロセス列挙用構造体 ---
    MAX_PATH = 260

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wt.DWORD),
            ("cntUsage", wt.DWORD),
            ("th32ProcessID", wt.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wt.DWORD),
            ("cntThreads", wt.DWORD),
            ("th32ParentProcessID", wt.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wt.DWORD),
            ("szExeFile", ctypes.c_wchar * MAX_PATH),
        ]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wt.BOOL
    kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wt.BOOL
    kernel32.CloseHandle.argtypes = [wt.HANDLE]

    # --- PoEプロセスのPIDを取得 ---
    target_names = {"pathofexile.exe", "pathofexilesteam.exe"}
    poe_pids = set()

    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        return (False, "プロセス一覧の取得に失敗しました")

    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
            while True:
                exe_name = pe.szExeFile.lower()
                if exe_name in target_names:
                    poe_pids.add(pe.th32ProcessID)
                if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                    break
    finally:
        kernel32.CloseHandle(snap)

    if not poe_pids:
        return (False, "PoEのプロセスが見つかりません")

    # --- TCP接続テーブル用構造体 ---
    class MIB_TCPROW_OWNER_PID(ctypes.Structure):
        _fields_ = [
            ("dwState", wt.DWORD),
            ("dwLocalAddr", wt.DWORD),
            ("dwLocalPort", wt.DWORD),
            ("dwRemoteAddr", wt.DWORD),
            ("dwRemotePort", wt.DWORD),
            ("dwOwningPid", wt.DWORD),
        ]

    class MIB_TCPTABLE_OWNER_PID(ctypes.Structure):
        _fields_ = [
            ("dwNumEntries", wt.DWORD),
            ("table", MIB_TCPROW_OWNER_PID * 1),
        ]

    # SetTcpEntry に渡す構造体（dwOwningPid なし）
    class MIB_TCPROW(ctypes.Structure):
        _fields_ = [
            ("dwState", wt.DWORD),
            ("dwLocalAddr", wt.DWORD),
            ("dwLocalPort", wt.DWORD),
            ("dwRemoteAddr", wt.DWORD),
            ("dwRemotePort", wt.DWORD),
        ]

    iphlpapi = ctypes.windll.iphlpapi

    # --- TCP接続テーブル取得 ---
    buf_size = wt.DWORD(0)
    iphlpapi.GetExtendedTcpTable(None, ctypes.byref(buf_size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)

    buf = (ctypes.c_byte * buf_size.value)()
    ret = iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(buf_size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
    if ret != NO_ERROR:
        return (False, f"TCP接続テーブルの取得に失敗しました (error={ret})")

    table = ctypes.cast(buf, ctypes.POINTER(MIB_TCPTABLE_OWNER_PID)).contents
    num_entries = table.dwNumEntries

    # テーブルの全エントリにアクセスするため、正しいサイズで再キャスト
    class MIB_TCPTABLE_OWNER_PID_FULL(ctypes.Structure):
        _fields_ = [
            ("dwNumEntries", wt.DWORD),
            ("table", MIB_TCPROW_OWNER_PID * num_entries),
        ]

    full_table = ctypes.cast(buf, ctypes.POINTER(MIB_TCPTABLE_OWNER_PID_FULL)).contents

    # --- PoEの接続を切断 ---
    disconnected = 0
    errors = 0
    for i in range(num_entries):
        row = full_table.table[i]
        if row.dwOwningPid in poe_pids:
            tcp_row = MIB_TCPROW()
            tcp_row.dwState = MIB_TCP_STATE_DELETE_TCB
            tcp_row.dwLocalAddr = row.dwLocalAddr
            tcp_row.dwLocalPort = row.dwLocalPort
            tcp_row.dwRemoteAddr = row.dwRemoteAddr
            tcp_row.dwRemotePort = row.dwRemotePort
            ret = iphlpapi.SetTcpEntry(ctypes.byref(tcp_row))
            if ret == NO_ERROR:
                disconnected += 1
            else:
                errors += 1

    if disconnected > 0:
        msg = f"{disconnected}本のTCP接続を切断しました"
        if errors > 0:
            msg += f"（{errors}本は失敗）"
        return (True, msg)
    elif errors > 0:
        return (False, f"TCP接続の切断に失敗しました（{errors}本）")
    else:
        return (False, "PoEのTCP接続が見つかりませんでした")
