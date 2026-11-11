import sys
import time
import random
from dataclasses import dataclass

FILES = "abcdefgh"
VALUES = {"p": 100, "n": 320, "b": 335, "r": 500, "q": 900, "k": 0}
KNIGHT = (-33, -31, -18, -14, 14, 18, 31, 33)
BISHOP = (-17, -15, 15, 17)
ROOK = (-16, -1, 1, 16)
KING = (-17, -16, -15, -1, 1, 15, 16, 17)
MATE = 100000
INF = 1000000
MAX_PLY = 128


def valid(s):
    return 0 <= s < 128 and not s & 0x88


def square_name(s):
    return FILES[s & 7] + str(8 - (s >> 4))


def parse_square(s):
    if len(s) != 2 or s[0] not in FILES or s[1] not in "12345678":
        return None
    return (8 - int(s[1])) * 16 + FILES.index(s[0])


def color(p):
    return 0 if p == "." else 1 if p.isupper() else -1


@dataclass(frozen=True, slots=True)
class Move:
    start: int
    end: int
    promotion: str = ""
    flag: str = ""

    def uci(self):
        return square_name(self.start) + square_name(self.end) + self.promotion


class Board:
    def __init__(self):
        rows = ("rnbqkbnr", "pppppppp", "........", "........", "........", "........", "PPPPPPPP", "RNBQKBNR")
        self.squares = ["."] * 128
        for r, row in enumerate(rows):
            for f, p in enumerate(row):
                self.squares[r * 16 + f] = p
        self.turn = 1
        self.castling = 15
        self.ep = -1
        self.halfmove = 0
        self.fullmove = 1

    @classmethod
    def from_fen(cls, fen):
        fields = fen.split()
        if len(fields) != 6:
            raise ValueError("FEN must contain six fields")
        b = cls.__new__(cls)
        b.squares = ["."] * 128
        rows = fields[0].split("/")
        if len(rows) != 8:
            raise ValueError("Invalid FEN board")
        for r, row in enumerate(rows):
            f = 0
            for ch in row:
                if ch.isdigit() and ch in "12345678":
                    f += int(ch)
                elif ch in "prnbqkPRNBQK" and f < 8:
                    b.squares[r * 16 + f] = ch
                    f += 1
                else:
                    raise ValueError("Invalid FEN rank")
            if f != 8:
                raise ValueError("Invalid FEN rank")
        if b.squares.count("K") != 1 or b.squares.count("k") != 1:
            raise ValueError("FEN must contain one king of each color")
        if fields[1] not in ("w", "b"):
            raise ValueError("Invalid FEN active color")
        b.turn = 1 if fields[1] == "w" else -1
        b.castling = sum(bit for flag, bit in zip("KQkq", (1, 2, 4, 8)) if flag in fields[2]) if fields[2] != "-" else 0
        if fields[2] != "-" and any(ch not in "KQkq" for ch in fields[2]):
            raise ValueError("Invalid FEN castling rights")
        b.ep = -1 if fields[3] == "-" else parse_square(fields[3])
        if fields[3] != "-" and b.ep is None:
            raise ValueError("Invalid FEN en-passant square")
        b.halfmove, b.fullmove = int(fields[4]), int(fields[5])
        return b

    def fen(self):
        rows = []
        for r in range(8):
            row, empty = "", 0
            for f in range(8):
                p = self.squares[r * 16 + f]
                if p == ".":
                    empty += 1
                else:
                    row += str(empty) if empty else ""
                    empty = 0
                    row += p
            rows.append(row + (str(empty) if empty else ""))
        rights = "".join(x for x, bit in zip("KQkq", (1, 2, 4, 8)) if self.castling & bit) or "-"
        return f"{'/'.join(rows)} {'w' if self.turn == 1 else 'b'} {rights} {square_name(self.ep) if self.ep >= 0 else '-'} {self.halfmove} {self.fullmove}"

    def copy(self):
        b = Board.__new__(Board)
        b.squares = self.squares.copy()
        b.turn, b.castling, b.ep = self.turn, self.castling, self.ep
        b.halfmove, b.fullmove = self.halfmove, self.fullmove
        return b

    def king_square(self, side):
        return self.squares.index("K" if side == 1 else "k")

    def attacked(self, target, by_side):
        for start, piece in enumerate(self.squares):
            if not valid(start) or color(piece) != by_side:
                continue
            kind = piece.lower()
            if kind == "p":
                if target in (start - 16 * by_side - 1, start - 16 * by_side + 1):
                    return True
                continue
            directions = KNIGHT if kind == "n" else BISHOP if kind == "b" else ROOK if kind == "r" else BISHOP + ROOK if kind == "q" else KING
            for direction in directions:
                square = start + direction
                while valid(square):
                    if square == target:
                        return True
                    if self.squares[square] != "." or kind in ("n", "k"):
                        break
                    square += direction
        return False

    def in_check(self, side=None):
        side = self.turn if side is None else side
        return self.attacked(self.king_square(side), -side)

    def make_move(self, move):
        b = self.copy()
        s, t = move.start, move.end
        piece, captured = b.squares[s], b.squares[t]
        b.squares[s] = "."
        b.squares[t] = (move.promotion.upper() if b.turn == 1 else move.promotion.lower()) if move.promotion else piece
        if move.flag == "ep":
            b.squares[t + 16 * b.turn] = "."
        if move.flag == "castle":
            rf, rt = (s + 3, s + 1) if t > s else (s - 4, s - 1)
            b.squares[rt], b.squares[rf] = b.squares[rf], "."
        rook_rights = {119: 1, 112: 2, 7: 4, 0: 8}
        if piece == "K": b.castling &= ~3
        elif piece == "k": b.castling &= ~12
        if piece.lower() == "r": b.castling &= ~rook_rights.get(s, 0)
        if captured.lower() == "r": b.castling &= ~rook_rights.get(t, 0)
        b.ep = (s + t) // 2 if piece.lower() == "p" and abs(t - s) == 32 else -1
        b.halfmove = 0 if piece.lower() == "p" or captured != "." or move.flag == "ep" else b.halfmove + 1
        b.fullmove += b.turn == -1
        b.turn = -b.turn
        return b

    def null_move(self):
        b = self.copy()
        b.ep = -1
        b.halfmove += 1
        b.fullmove += b.turn == -1
        b.turn = -b.turn
        return b

    def pseudo_moves(self, captures_only=False):
        moves = []
        for start, piece in enumerate(self.squares):
            if not valid(start) or color(piece) != self.turn:
                continue
            kind = piece.lower()

            def add(end, flag=""):
                if self.squares[end].lower() == "k":
                    return
                if kind == "p" and end >> 4 in (0, 7):
                    moves.extend(Move(start, end, q, flag) for q in "qrbn")
                else:
                    moves.append(Move(start, end, "", flag))

            if kind == "p":
                direction = -16 * self.turn
                forward = start + direction
                if not captures_only and valid(forward) and self.squares[forward] == ".":
                    add(forward)
                    double = forward + direction
                    home = 6 if self.turn == 1 else 1
                    if start >> 4 == home and self.squares[double] == ".":
                        add(double)
                for offset in (-1, 1):
                    target = forward + offset
                    if valid(target):
                        if color(self.squares[target]) == -self.turn:
                            add(target)
                        elif target == self.ep and self.squares[target] == ".":
                            add(target, "ep")
                continue

            directions = KNIGHT if kind == "n" else BISHOP if kind == "b" else ROOK if kind == "r" else BISHOP + ROOK if kind == "q" else KING
            for direction in directions:
                target = start + direction
                while valid(target):
                    if color(self.squares[target]) == self.turn:
                        break
                    if not captures_only or self.squares[target] != ".":
                        add(target)
                    if self.squares[target] != "." or kind in ("n", "k"):
                        break
                    target += direction

            if kind == "k" and not captures_only:
                home = 116 if self.turn == 1 else 4
                rook = "R" if self.turn == 1 else "r"
                king_bit, queen_bit = (1, 2) if self.turn == 1 else (4, 8)
                if start == home and not self.in_check():
                    king_piece = self.squares[start]
                    self.squares[start] = "."
                    try:
                        if self.castling & king_bit and self.squares[start + 3] == rook and self.squares[start + 1] == self.squares[start + 2] == "." and not self.attacked(start + 1, -self.turn) and not self.attacked(start + 2, -self.turn):
                            add(start + 2, "castle")
                        if self.castling & queen_bit and self.squares[start - 4] == rook and self.squares[start - 1] == self.squares[start - 2] == self.squares[start - 3] == "." and not self.attacked(start - 1, -self.turn) and not self.attacked(start - 2, -self.turn):
                            add(start - 2, "castle")
                    finally:
                        self.squares[start] = king_piece
        return moves

    def legal_moves(self):
        return [m for m in self.pseudo_moves() if not self.make_move(m).in_check(self.turn)]

    def display(self):
        print()
        for rank in range(8):
            print(f" {8-rank}  " + " ".join(self.squares[rank * 16:rank * 16 + 8]))
        print("\n    a b c d e f g h")
        print("    White to move" if self.turn == 1 else "    Black to move")
        if self.in_check(): print("    CHECK!")
        print()


class Zobrist:
    def __init__(self):
        rng = random.Random(0xC0FFEE)
        self.pieces = {p: [rng.getrandbits(64) for _ in range(128)] for p in "PNBRQKpnbrqk"}
        self.castling = [rng.getrandbits(64) for _ in range(16)]
        self.ep = [rng.getrandbits(64) for _ in range(8)]
        self.turn = rng.getrandbits(64)

    def hash(self, b, include_clock=False):
        h = self.castling[b.castling]
        for s, p in enumerate(b.squares):
            if valid(s) and p != ".": h ^= self.pieces[p][s]
        if b.turn == -1: h ^= self.turn
        if b.ep >= 0: h ^= self.ep[b.ep & 7]
        if include_clock: h ^= (b.halfmove * 0x9E3779B97F4A7C15) & ((1 << 64) - 1)
        return h


def evaluate(b):
    mg, eg, phase = 0, 0, 0
    pawn_files = {1: [0] * 8, -1: [0] * 8}
    pawn_squares = {1: [], -1: []}
    bishops = {1: 0, -1: 0}
    non_pawn = {1: 0, -1: 0}
    for s, p in enumerate(b.squares):
        if not valid(s) or p == ".": continue
        c, k = color(p), p.lower()
        r, f = s >> 4, s & 7
        rr = 7-r if c == 1 else r
        center = 7 - (abs(3.5-f) + abs(3.5-r))
        value = VALUES[k]
        phase += {"q": 4, "r": 2, "b": 1, "n": 1}.get(k, 0)
        if k == "p":
            pawn_files[c][f] += 1
            pawn_squares[c].append((r, f))
            mg += c * (value + rr * 9 + int(center * 3))
            eg += c * (value + rr * 14 + int(center * 5))
        elif k == "n":
            mg += c * (value + int(center * 9) - (18 if rr == 0 else 0))
            eg += c * (value + int(center * 5))
            non_pawn[c] += value
        elif k == "b":
            bishops[c] += 1
            mg += c * (value + int(center * 5))
            eg += c * (value + int(center * 6))
            non_pawn[c] += value
        elif k == "r":
            mg += c * (value + rr * 2)
            eg += c * (value + rr * 4)
            non_pawn[c] += value
        elif k == "q":
            mg += c * (value + int(center * 2))
            eg += c * (value + int(center * 4))
            non_pawn[c] += value
        else:
            mg += c * (-int(center * 5) if phase > 12 else int(center * 10))
            eg += c * (int(center * 12))
    for c in (1, -1):
        for f, count in enumerate(pawn_files[c]):
            if count > 1: mg -= c * (count - 1) * 14
            if count and not (pawn_files[c][f-1] if f else 0) and not (pawn_files[c][f+1] if f < 7 else 0):
                mg -= c * 12
        if bishops[c] >= 2:
            mg += c * 32
            eg += c * 45
        enemy = pawn_squares[-c]
        for r, f in pawn_squares[c]:
            passed = not any(abs(ef-f) <= 1 and ((er < r) if c == 1 else (er > r)) for er, ef in enemy)
            if passed:
                advance = 7-r if c == 1 else r
                mg += c * advance * advance * 3
                eg += c * advance * advance * 8
    phase = min(24, phase)
    score = (mg * phase + eg * (24-phase)) // 24
    return score if b.turn == 1 else -score


class Engine:
    def __init__(self, hash_mb=32):
        self.zobrist = Zobrist()
        self.tt = {}
        self.tt_limit = max(10000, hash_mb * 1800)
        self.killers = [[None, None] for _ in range(MAX_PLY)]
        self.history = {}
        self.countermoves = {}
        self.nodes = 0
        self.qnodes = 0
        self.start_time = 0
        self.deadline = float("inf")
        self.node_limit = 0
        self.stopped = False
        self.pv = [[] for _ in range(MAX_PLY)]
        self.pv_length = [0] * MAX_PLY
        self.position_history = []
        self.repetition = {}

    def check_time(self):
        if self.node_limit and self.nodes >= self.node_limit:
            self.stopped = True
        elif (self.nodes & 2047) == 0 and time.monotonic() >= self.deadline:
            self.stopped = True
        if self.stopped:
            raise TimeoutError

    def draw(self, b, key):
        if b.halfmove >= 100 or self.repetition.get(key, 0) >= 3:
            return True
        return False

    def push_key(self, key):
        self.repetition[key] = self.repetition.get(key, 0) + 1

    def pop_key(self, key):
        n = self.repetition[key] - 1
        if n: self.repetition[key] = n
        else: del self.repetition[key]

    def move_score(self, b, m, tt_move, ply, previous):
        if m == tt_move: return 2_000_000
        target = b.squares[m.end]
        attacker = b.squares[m.start]
        if target != "." or m.flag == "ep":
            victim = VALUES["p"] if m.flag == "ep" else VALUES[target.lower()]
            return 1_000_000 + victim * 16 - VALUES[attacker.lower()]
        if m.promotion: return 900_000 + VALUES[m.promotion]
        child = b.make_move(m)
        if child.in_check():
            return 850_000 + self.history.get((b.turn, m.start, m.end), 0)
        if ply < MAX_PLY:
            if m == self.killers[ply][0]: return 800_000
            if m == self.killers[ply][1]: return 790_000
        if previous and self.countermoves.get(previous) == m: return 780_000
        return self.history.get((b.turn, m.start, m.end), 0)

    def ordered(self, b, moves, tt_move, ply, previous):
        return sorted(moves, key=lambda m: self.move_score(b, m, tt_move, ply, previous), reverse=True)

    def record_cutoff(self, b, m, depth, ply, previous):
        if b.squares[m.end] == "." and m.flag != "ep" and not m.promotion:
            if ply < MAX_PLY and m != self.killers[ply][0]:
                self.killers[ply][1] = self.killers[ply][0]
                self.killers[ply][0] = m
            self.history[(b.turn, m.start, m.end)] = min(1_000_000, self.history.get((b.turn, m.start, m.end), 0) + depth * depth * 32)
            if previous: self.countermoves[previous] = m

    def quiescence(self, b, alpha, beta, ply, qply=0):
        self.qnodes += 1
        if (self.qnodes & 2047) == 0: self.check_time()
        in_check = b.in_check()
        stand = -INF if in_check else evaluate(b)
        if not in_check:
            if stand >= beta: return beta
            alpha = max(alpha, stand)
        if qply >= 16: return stand if not in_check else evaluate(b)
        moves = b.legal_moves()
        if not moves: return -MATE + ply if in_check else 0
        if not in_check:
            moves = [m for m in moves if b.squares[m.end] != "." or m.flag == "ep" or m.promotion]
        moves = self.ordered(b, moves, None, ply, None)
        for m in moves:
            child = b.make_move(m)
            child_key = self.zobrist.hash(child)
            self.push_key(child_key)
            try:
                score = -self.quiescence(child, -beta, -alpha, ply + 1, qply + 1)
            finally:
                self.pop_key(child_key)
            if score >= beta: return beta
            if score > alpha: alpha = score
        return alpha

    def search(self, b, depth, alpha, beta, ply=0, allow_null=True, previous=None):
        self.nodes += 1
        if self.nodes & 2047 == 0: self.check_time()
        self.pv_length[ply] = ply
        rep_key = self.zobrist.hash(b)
        key = self.zobrist.hash(b, True)
        if ply and self.draw(b, rep_key): return 0
        if ply >= MAX_PLY - 1: return evaluate(b)
        in_check = b.in_check()
        if in_check: depth += 1
        if depth <= 0: return self.quiescence(b, alpha, beta, ply)

        alpha = max(alpha, -MATE + ply)
        beta = min(beta, MATE - ply - 1)
        if alpha >= beta:
            return alpha

        original_alpha = alpha
        tt_entry = self.tt.get(key)
        tt_move = tt_entry[3] if tt_entry else None
        if tt_entry and tt_entry[0] >= depth and ply:
            _, tt_score, flag, _ = tt_entry
            if flag == 0: return tt_score
            if flag == 1 and tt_score >= beta: return tt_score
            if flag == -1 and tt_score <= alpha: return tt_score

        if allow_null and depth >= 3 and not in_check and b.halfmove < 99:
            if any(valid(s) and color(p) == b.turn and p.lower() in "nbrq" for s, p in enumerate(b.squares)):
                reduction = 2 + depth // 4
                score = -self.search(b.null_move(), depth - 1 - reduction, -beta, -beta + 1, ply + 1, False, None)
                if score >= beta:
                    return beta

        moves = self.ordered(b, b.legal_moves(), tt_move, ply, previous)
        if not moves: return -MATE + ply if in_check else 0
        best_score, best_move = -INF, None
        legal_count = 0
        for m in moves:
            child = b.make_move(m)
            gives_check = child.in_check()
            capture = b.squares[m.end] != "." or m.flag == "ep"
            quiet = not capture and not m.promotion
            legal_count += 1
            reduction = 0
            if depth >= 3 and legal_count >= 4 and quiet and not in_check and not gives_check:
                reduction = int(1 + (depth >= 6 and legal_count >= 8))
            child_key = self.zobrist.hash(child)
            self.push_key(child_key)
            try:
                if legal_count == 1:
                    score = -self.search(child, depth - 1, -beta, -alpha, ply + 1, True, m)
                else:
                    score = -self.search(child, depth - 1 - reduction, -alpha - 1, -alpha, ply + 1, True, m)
                    if score > alpha and (reduction or score < beta):
                        score = -self.search(child, depth - 1, -beta, -alpha, ply + 1, True, m)
            finally:
                self.pop_key(child_key)
            if score > best_score:
                best_score, best_move = score, m
            if score > alpha:
                alpha = score
                self.pv[ply] = [m] + self.pv[ply + 1][:self.pv_length[ply + 1] - (ply + 1)]
                self.pv_length[ply] = len(self.pv[ply]) + ply
            if alpha >= beta:
                if quiet: self.record_cutoff(b, m, depth, ply, previous)
                break
        flag = -1 if best_score <= original_alpha else 1 if best_score >= beta else 0
        if len(self.tt) >= self.tt_limit:
            self.tt.clear()
        self.tt[key] = (depth, best_score, flag, best_move)
        return best_score

    def choose_move(self, board, max_depth=12, seconds=5.0, nodes=0, history=None):
        moves = board.legal_moves()
        if not moves: return None, 0, 0.0
        self.nodes = self.qnodes = 0
        self.stopped = False
        self.start_time = time.monotonic()
        self.deadline = self.start_time + seconds if seconds else float("inf")
        self.node_limit = nodes
        self.repetition.clear()
        for old in history or []:
            self.push_key(self.zobrist.hash(old))
        root_rep_key = self.zobrist.hash(board)
        root_key = self.zobrist.hash(board, True)
        self.push_key(root_rep_key)
        best_move, best_score = moves[0], evaluate(board)
        previous_score = 0
        for depth in range(1, max_depth + 1):
            window = 35 if depth >= 4 else INF
            alpha, beta = (previous_score - window, previous_score + window) if window != INF else (-INF, INF)
            try:
                while True:
                    score = self.search(board, depth, alpha, beta)
                    if score <= alpha:
                        alpha, beta = -INF, (alpha + beta) // 2
                        continue
                    if score >= beta:
                        alpha, beta = (alpha + beta) // 2, INF
                        continue
                    break
                root_entry = self.tt.get(root_key)
                if root_entry and root_entry[3]: best_move = root_entry[3]
                best_score, previous_score = score, score
                pv = self.pv[0][:]
                pv_text = " ".join(m.uci() for m in pv)
                elapsed = max(0.001, time.monotonic() - self.start_time)
                print(f"  depth {depth:2}  score {score/100:+.2f}  nodes {self.nodes+self.qnodes:,}  time {elapsed:.2f}s  nps {int((self.nodes+self.qnodes)/elapsed):,}  pv {pv_text}")
            except TimeoutError:
                break
        self.pop_key(root_rep_key)
        elapsed = time.monotonic() - self.start_time
        return best_move, best_score, elapsed


def move_to_san(board, move, legal):
    piece = board.squares[move.start]
    target = board.squares[move.end]
    kind = piece.upper()
    if move.flag == "castle": return "O-O" if move.end > move.start else "O-O-O"
    capture = target != "." or move.flag == "ep"
    if kind == "P":
        text = FILES[move.start & 7] + "x" if capture else ""
    else:
        text = kind
        alternatives = [m for m in legal if m.start != move.start and m.end == move.end and board.squares[m.start].upper() == kind]
        if alternatives:
            same_file = any((m.start & 7) == (move.start & 7) for m in alternatives)
            same_rank = any((m.start >> 4) == (move.start >> 4) for m in alternatives)
            text += FILES[move.start & 7] if not same_file else str(8 - (move.start >> 4)) if not same_rank else square_name(move.start)
        if capture: text += "x"
    text += square_name(move.end)
    if move.promotion: text += "=" + move.promotion.upper()
    result = board.make_move(move)
    if result.in_check(): text += "+" if result.legal_moves() else "#"
    return text


def parse_move(text, board, legal):
    normalized = text.strip().lower().rstrip("+#?!")
    san = normalized.replace("=", "")
    castle = san.replace("-", "")
    if castle in ("o-o", "00"):
        return next((m for m in legal if m.flag == "castle" and m.end > m.start), None)
    if castle in ("o-o-o", "000"):
        return next((m for m in legal if m.flag == "castle" and m.end < m.start), None)
    if len(normalized) in (4, 5):
        start, end = parse_square(normalized[:2]), parse_square(normalized[2:4])
        if start is not None and end is not None:
            promotion = normalized[4] if len(normalized) == 5 else "q"
            for move in legal:
                if move.start == start and move.end == end:
                    if move.promotion and move.promotion == promotion: return move
                    if not move.promotion and len(normalized) == 4: return move
    for move in legal:
        candidate = move_to_san(board, move, legal).lower().replace("=", "").rstrip("+#?!")
        if san == candidate: return move
    return None


def insufficient_material(board):
    pieces = [(p.lower(), ((s >> 4) + (s & 7)) % 2) for s, p in enumerate(board.squares) if valid(s) and p != "." and p.lower() != "k"]
    return not pieces or len(pieces) == 1 and pieces[0][0] in ("b", "n") or all(p == "b" for p, _ in pieces) and len({sq for _, sq in pieces}) == 1


def game_result(board, position_counts):
    moves = board.legal_moves()
    if not moves:
        return ("1-0" if board.turn == -1 else "0-1") if board.in_check() else "1/2-1/2"
    if insufficient_material(board) or board.halfmove >= 150 or position_counts.get(board.fen().split()[0] + board.fen().split()[1] + board.fen().split()[2] + board.fen().split()[3], 0) >= 5:
        return "1/2-1/2"
    return None


def perft(board, depth):
    if depth == 0: return 1
    return sum(perft(board.make_move(m), depth - 1) for m in board.legal_moves())



OPENING_BOOK = [
    ("Italian Game", "e2e4 e7e5 g1f3 b8c6 f1c4 f8c5 d2d3 g8f6", 5),
    ("Ruy Lopez", "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 b5a4 g8f6", 5),
    ("Scotch Game", "e2e4 e7e5 g1f3 b8c6 d2d4 e5d4 f3d4", 4),
    ("Petrov Defense", "e2e4 e7e5 g1f3 g8f6 f3e5 d7d6 e5f3 f6e4", 3),
    ("Sicilian Defense", "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3", 6),
    ("Sicilian Najdorf", "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6", 4),
    ("French Defense", "e2e4 e7e6 d2d4 d7d5 b1c3 g8f6", 4),
    ("Caro-Kann Defense", "e2e4 c7c6 d2d4 d7d5 b1c3 d5e4 c3e4", 4),
    ("Scandinavian Defense", "e2e4 d7d5 e4d5 d8d5 b1c3 d5a5", 3),
    ("Pirc Defense", "e2e4 d7d6 d2d4 g8f6 b1c3 g7g6", 3),
    ("Queen's Gambit Declined", "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6 g1f3", 5),
    ("Slav Defense", "d2d4 d7d5 c2c4 c7c6 g1f3 g8f6 b1c3 d5c4", 4),
    ("King's Indian Defense", "d2d4 g8f6 c2c4 g7g6 b1c3 f8g7 e2e4 d7d6", 5),
    ("Nimzo-Indian Defense", "d2d4 g8f6 c2c4 e7e6 b1c3 f8b4", 4),
    ("Grunfeld Defense", "d2d4 g8f6 c2c4 g7g6 b1c3 d7d5", 3),
    ("English Opening", "c2c4 e7e5 b1c3 g8f6 g2g3 d7d5", 3),
    ("Réti Opening", "g1f3 d7d5 g2g3 g8f6 f1g2", 3),
]


def mate_in_one(board, legal_moves=None):
    for move in legal_moves if legal_moves is not None else board.legal_moves():
        child = board.make_move(move)
        if child.in_check() and not child.legal_moves():
            return move
    return None


def choose_book_move(move_history, legal_moves):
    choices = {}
    for name, sequence, weight in OPENING_BOOK:
        moves = sequence.split()
        if len(move_history) < len(moves) and move_history == moves[:len(move_history)]:
            uci = moves[len(move_history)]
            if any(move.uci() == uci for move in legal_moves):
                entry = choices.setdefault(uci, [0, []])
                entry[0] += weight
                entry[1].append(name)
    if not choices:
        return None, None
    uci = random.choices(list(choices), weights=[entry[0] for entry in choices.values()], k=1)[0]
    names = choices[uci][1]
    return next(move for move in legal_moves if move.uci() == uci), random.choice(names)



CHAT_LINES = {
    "hello": ["yo", "the games practically over already", "glhf", "if takes takes takes takes"],
    "opening": ["bro studied his opening theory", "do you know this line", "eh pretty good game", "ima activate"],
    "develop": ["good development brodie", "activation nation", "just get everything out"],
    "capture": ["i hate you", "why", "i loved that piece like a son", "brilliant sacrifice bro trust"],
    "check": ["check", "shack", "ALIEN GAMBIT ALIEN GAMBIT"],
    "castle": ["yeah be scared", "castle like a good boy", "who do u think u are"],
    "queen": ["lmao with the queen", "i heart the queen", "yo bro chess yams 8 oclock dont make it obvious"],
    "blunder": ["LMAO", "yeah ggs bro", "LOL HOW DID U MESS THAT UP"],
    "thinking": ["uhhh", "hmmmmm", "idk tbh", "im debating whether i should blunder for fun"],
    "good": ["wow", "ok", "great", "w move"],
    "mate": ["yeah bro hop off chess", "GG FRIGGEN EZ"],
    "win": ["I HATE YOU", "best of 3 trust", "why bro"],
    "draw": ["bro drew :sob:", "how bro"],
}

def chat_say(message, enabled=True):
    if enabled:
        print(f"\nBot: {message}")

def chat_random(kind):
    return random.choice(CHAT_LINES[kind])

def chat_after_player(board_before, move, board_after):
    piece = board_before.squares[move.start]
    captured = board_before.squares[move.end] != "." or move.flag == "ep"
    if board_after.in_check():
        chat_say(chat_random("check"))
    elif move.flag == "castle":
        chat_say(chat_random("castle"))
    elif captured:
        chat_say(chat_random("capture"))
    elif piece.lower() == "q":
        chat_say(chat_random("queen"))
    elif board_before.fullmove <= 4:
        chat_say(chat_random("opening"))
    elif random.random() < 0.12:
        chat_say(chat_random("good"))

def chat_after_engine(board_before, move, board_after, opening=None):
    legal = board_after.legal_moves()
    if board_after.in_check() and not legal:
        chat_say(chat_random("mate"))
    elif board_after.in_check():
        chat_say(chat_random("check"))
    elif not legal:
        chat_say(chat_random("draw"))
    elif opening:
        chat_say(f"welp guess we doing the {opening}")
    elif move.flag == "castle":
        chat_say(chat_random("castle"))
    elif random.random() < 0.16:
        chat_say(chat_random("thinking"))

def main():
    board = Board()
    engine = Engine(64)
    history = []
    positions = [board.copy()]
    move_history = []
    depth, think_time = 12, 5.0
    use_book = True
    chat_enabled = True
    print("-- Leonbot --")
    print("You play White. Engine plays Black.")
    chat_say(chat_random("hello"), chat_enabled)
    print("Enter SAN or UCI moves. Commands: help, undo, board, fen, depth N, time N, book on/off, openings, chat on/off, quit.\n")
    while True:
        board.display()
        legal = board.legal_moves()
        if not legal:
            print("Checkmate!", "White wins!" if board.turn == -1 else "Black wins!") if board.in_check() else print("Draw by stalemate.")
            break
        rep_key = engine.zobrist.hash(board)
        repetitions = sum(engine.zobrist.hash(p) == rep_key for p in positions)
        if board.halfmove >= 150 or repetitions >= 5:
            print("Draw by the seventy-five-move rule." if board.halfmove >= 150 else "Draw by fivefold repetition.")
            break
        claim = "50-move rule" if board.halfmove >= 100 else "threefold repetition" if repetitions >= 3 else ""
        if claim:
            print(f"Draw claim available: {claim} (type 'claim').")
        if board.turn == 1:
            command = input("Your move > ").strip()
            low = command.lower()
            if low == "quit": break
            if low == "help":
                print("Moves: e4, Nf3, O-O, e2e4, e7e8q. Commands: undo, board, fen, claim, depth N, time N, perft N, book on/off, openings, chat on/off, quit.")
                continue
            if low == "board": continue
            if low == "fen": print(board.fen()); continue
            if low == "openings":
                print("Built-in openings:")
                for name in dict.fromkeys(entry[0] for entry in OPENING_BOOK): print("  " + name)
                continue
            if low in ("book on", "book off"):
                use_book = low.endswith("on")
                print("Opening book " + ("enabled." if use_book else "disabled."))
                continue
            if low in ("chat on", "chat off"):
                chat_enabled = low.endswith("on")
                print("Bot chat " + ("enabled." if chat_enabled else "disabled."))
                continue
            if low == "claim":
                if claim:
                    print("Draw claimed by", claim + ".")
                    break
                print("No draw claim is currently available.")
                continue
            if low.startswith("depth "):
                try: depth = max(1, min(30, int(low.split()[1])))
                except (ValueError, IndexError): print("Usage: depth 1..30")
                continue
            if low.startswith("time "):
                try: think_time = max(0.1, min(300, float(low.split()[1])))
                except (ValueError, IndexError): print("Usage: time seconds")
                continue
            if low.startswith("perft "):
                try:
                    d = int(low.split()[1]); t = time.monotonic(); count = perft(board, d)
                    print(f"perft({d}) = {count:,} in {time.monotonic()-t:.3f}s")
                except (ValueError, IndexError): print("Usage: perft depth")
                continue
            if low == "undo":
                if history:
                    board = history.pop()
                    positions.pop()
                    if move_history: move_history.pop()
                    if history and board.turn == -1:
                        board = history.pop()
                        positions.pop()
                        if move_history: move_history.pop()
                else: print("Nothing to undo.")
                continue
            move = parse_move(command, board, legal)
            if move is None:
                print("That is not a legal move.")
                continue
            print("You played:", move_to_san(board, move, legal))
            before = board
            board = board.make_move(move)
            history.append(before.copy())
            move_history.append(move.uci())
            positions.append(board.copy())
            chat_after_player(before, move, board)
            continue
        else:
            forced_mate = mate_in_one(board, legal)
            book_move, opening = choose_book_move(move_history, legal) if use_book else (None, None)
            if forced_mate:
                move = forced_mate
                print(f"Leonbot plays {move_to_san(board, move, legal)} ({move.uci()})  [checkmate]")
            elif book_move:
                move = book_move
                print(f"Leonbot plays {move_to_san(board, move, legal)} ({move.uci()})  [book: {opening}]")
            else:
                print(f"Leonbot thinking (depth {depth}, {think_time:g}s)...")
                move, score, elapsed = engine.choose_move(board, depth, think_time, history=positions[:-1])
                if move is None: break
                mate = (MATE - abs(score)) if abs(score) >= MATE - MAX_PLY else 0
                detail = f"  mate in {(mate + 1) // 2}" if mate else f"  eval {score/100:+.2f}"
                print(f"Leonbot plays {move_to_san(board, move, legal)} ({move.uci()}){detail}  {elapsed:.2f}s")
        before = board
        history.append(board.copy())
        move_history.append(move.uci())
        board = board.make_move(move)
        positions.append(board.copy())
        if before.turn == -1:
            chat_after_engine(before, move, board, opening if book_move else None)
    print("Thanks for playing.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
        sys.exit(0)
