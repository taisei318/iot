# 設計ドキュメント (案2: MapReduceで分類)

## 1. 概要

スプレセンスの3軸加速度センサ(KX126)から得られる生データを、エッジ→クラウドに集約し、
**MapReduce で時間窓ごとに特徴量化・分類** することで「静止 (STILL) / 歩行 (WALK) / 走行 (RUN)」を判定する。
判定結果は Notebook で集計・可視化する。

エッジ実験(センサ取得・FTP転送)とクラウド実験(MongoDB・MapReduce)の両要素を1本のパイプラインで通すことが目的。

---

## 2. 目的とねらい

- これまでに学んだ要素を **一本の縦パイプライン** として統合する
- 「生データの収集はエッジ、特徴量計算と分類はクラウド」という現実的な分担を体験する
- MapReduce に **意味のある仕事(時間窓ごとの分散→分類)** を担わせる
- しきい値や時間窓を変えても再分類できるよう、生データを残す設計にする

---

## 3. 全体アーキテクチャ

```
+-----------+      Serial(USB)       +-----------+   FTP/直接    +-----------+   query    +-----------+
| Spresense | --------------------> | Host A    | ------------> |  Host C   | --------> | Host B    |
| (KX126)   |   "x,y,z" @20Hz       | receiver  |   10秒ごと    |  MongoDB  |           | MapReduce |
|           |                       | (PC/Pi)   |   CSV/insert  |  Server   |           |  + 可視化 |
+-----------+                       +-----------+               +-----------+           +-----------+
```

- **Spresense**: 加速度 (x, y, z) を 20Hz でシリアル送信
- **Host A**: シリアル受信し、生データを 10 秒ごとにまとめて Host C へ転送
- **Host C**: MongoDB を起動。Host A からの書き込みを受け、Host B のクエリに応答
- **Host B**: MongoDB からデータを取得し、MapReduce で時間窓集計+分類、Notebook で可視化

物理マシン数は最小2台でも可(Host A = C、Host B = C など兼用)。

---

## 4. データフロー詳細

### 4.1 Spresense → Host A
- 形式: `x,y,z\n`(単位: G、改行区切り)
- ボーレート: 115200
- サンプリング: 約20Hz(`delay(50)`)
- 常時送信(コマンド制御なし)

### 4.2 Host A の処理 (`raspi/receiver.py`)
- シリアルから1行ずつ受信し、`{t, x, y, z}` のリストにバッファ
- 10秒経過したらまとめて
  - **方式①(FTP経由)**: CSVに書き出し → Host C の FTP サーバへアップロード → 別プロセスで MongoDB へ ingest
  - **方式②(直接)**: Host C の MongoDB に `insert_many` で直接書き込む
- 方式②のほうがシンプル。FTP は中間ステージとして残してもよい

ドキュメント例:
```json
{
  "t": "2026-05-14T14:23:01.420",
  "x": 0.020,
  "y": 0.100,
  "z": 1.040
}
```

### 4.3 Host C (MongoDB)
- DB名: `iot`
- Collection: `accel_raw`
- インデックス: `t` (時系列クエリ高速化のため昇順インデックス)
- 推定サイズ: 20Hz × 1人 × 1時間 = 約72,000ドキュメント

### 4.4 Host B (MapReduce + 可視化)
- MongoDB から期間指定で取得 → MapReduce へ流す
- mapper/reducer は 5週目で作った `server.py / client.py / mapper.py / reducer.py` を流用
- 集計結果を Notebook で読み込んでグラフ化

---

## 5. 分類アルゴリズム

### 5.1 特徴量
- **ノルム**: `|a| = sqrt(x² + y² + z²)`
- 時間窓ごとに **ノルムの分散** を計算
- 静止時はほぼ重力 (約1.0G) で分散ほぼ0
- 動きが大きいほど分散が増大

### 5.2 しきい値(初期値、要調整)
| 分類 | 分散 (G²) の範囲 |
|---|---|
| STILL | `var < 0.02` |
| WALK  | `0.02 ≤ var < 0.50` |
| RUN   | `var ≥ 0.50` |

実測しながら、走行/歩行データのヒストグラムを見て決定する。
しきい値検討は発表ネタとして1スライド使える(「実測してこう決めた」を語る)。

### 5.3 時間窓
- 窓幅: 1秒(20サンプル @ 20Hz)
- ステップ: 1秒(非オーバーラップ)
- 1日のデータでも窓数は最大86,400で MapReduce で十分捌ける

---

## 6. MapReduce 設計

### 6.1 入力
MongoDB から取得した生データ 1ドキュメント = 1レコード:
```
t, x, y, z
```

### 6.2 mapper
1. タイムスタンプを 1 秒単位に丸める → これが窓キー
2. ノルム `|a|` を計算
3. 出力: `key=window_t, value=(norm, 1)` ※ 後で分散を計算するため

擬似コード:
```python
for line in stdin:
    t, x, y, z = parse(line)
    window = floor_to_second(t)
    norm = sqrt(x*x + y*y + z*z)
    print(f"{window}\t{norm}")
```

### 6.3 reducer
窓ごとに集まったノルム列から
- 平均、分散を計算
- 分散から STILL/WALK/RUN を分類
- 出力: `window_t, count, mean, var, state`

擬似コード:
```python
for window, norms in groupby(stdin):
    mean = sum(norms)/n
    var  = sum((x-mean)**2 for x in norms)/n
    state = classify(var)
    print(f"{window}\t{n}\t{mean}\t{var}\t{state}")
```

### 6.4 拡張集計
分類結果を元に2段目の MapReduce でさらに集計:
- 状態別の合計時間(累積秒数)
- 時間帯別の出現頻度(例: 各時間に何秒 RUN だったか)
- 1分ごとの代表状態(モード)

---

## 7. 可視化(Notebook)

`final/host_b/analysis.ipynb` で以下を実装:

1. **時系列**: 横軸=時刻、縦軸=ノルム平均、色=分類状態 のラインプロット
2. **状態別ヒストグラム**: 分散値の分布(分類しきい値の妥当性チェック)
3. **状態別積み上げ棒**: 1分単位で STILL/WALK/RUN の秒数
4. **状態遷移**: STILL→WALK→RUN の遷移回数(matplotlib のヒートマップ等)

---

## 8. ファイル構成

```
final/
├── docs/
│   ├── memo.md            最初のメモ
│   └── design.md          このファイル
├── arduino/
│   └── sender/
│       └── sender.ino     KX126 常時送信 (完成)
├── raspi/                 ホストA
│   ├── receiver.py        シリアル受信+10秒バッファ
│   ├── ftp.py             FTP送信(残すなら)
│   └── mongo_writer.py    [新規] MongoDB へ insert_many する版
├── server/                ホストC (FTP/MongoDB)
│   ├── ftp_server.py      FTP受信(残すなら)
│   └── ingest.py          [新規] recv/*.csv → MongoDB ingest
└── host_b/                ホストB (MapReduce + 可視化)
    ├── exporter.py        [新規] MongoDB → 標準入力に流す
    ├── mapper.py          [新規] 5週目を流用・改造
    ├── reducer.py         [新規] 5週目を流用・改造
    ├── server.py / client.py  [新規] 5週目を流用
    └── analysis.ipynb     [新規] 可視化
```

ホストAとCを同一マシンで動かす場合は `mongo_writer.py` 1本に簡略化できる。

---

## 9. 実装マイルストーン

### M1: エッジ→ MongoDB 直送(最小ライン)
- [x] Spresense → receiver.py で stdout 表示
- [x] FTP送信
- [ ] receiver.py に MongoDB 直書き込みを追加(`mongo_writer.py` または receiver.py 拡張)
- [ ] MongoDB サーバ起動、コレクション作成、インデックス付与

### M2: MapReduce で分類
- [ ] 5週目の mapper/reducer をベースに窓集計版を作成
- [ ] MongoDB から1日分エクスポートして MapReduce 実行
- [ ] 出力(窓ごとの state)を CSV で受け取る

### M3: 可視化
- [ ] Notebook で時系列ライン + 状態色分け
- [ ] ヒストグラムでしきい値検証
- [ ] 状態別積み上げグラフ

### M4: 発展(余力次第)
- [ ] しきい値スイープを MapReduce で並列実行
- [ ] 1分単位の代表状態への二段集計
- [ ] リアルタイム性のあるダッシュボード

---

## 10. 発表ストーリー(10分)

| 時間 | 内容 |
|---|---|
| 0:00-0:30 | タイトル・目的 |
| 0:30-2:00 | システム構成図(本ドキュメントの図) |
| 2:00-3:30 | エッジ側実装(Spresense + receiver) |
| 3:30-5:00 | MongoDB スキーマ + 取り込み |
| 5:00-7:00 | MapReduce 設計(mapper/reducer 擬似コード+結果) |
| 7:00-8:30 | 可視化結果 |
| 8:30-9:30 | 工夫した点 / 苦労した点 |
| 9:30-10:00 | まとめ |

### 工夫した点(候補)
- **生データを残す設計**: しきい値変更・再分類が可能
- **時間窓ベースの分類**: 単発のノイズを除外できる
- **MapReduce にロジックを置く**: 計算を分散できる構造に
- **FTP/MongoDB の責務分離**: 取り込みと分析が独立して動かせる

### 苦労した点(候補)
- 分散しきい値の決定(実測の試行錯誤)
- 時間窓境界のタイムスタンプ処理
- 複数ホスト間のネットワーク・FW 設定

---

## 11. 未決事項

- [ ] **MongoDB ホスティング**: 自分のPC上 / 既存の演習用サーバ / Atlas
- [ ] **Host A → MongoDB の経路**: FTP経由 ingest か、receiver から pymongo 直送か
- [ ] **時間窓**: 1秒固定でいくか、可変にして実験するか
- [ ] **データ収集計画**: 何分の STILL/WALK/RUN を収集するか、被験者は1人で十分か

---

## 12. 用語

- **エッジ**: Spresense + 受信PC側。データの取得・前処理を担う
- **クラウド**: MongoDB + MapReduce + 可視化側。データの蓄積・分析を担う
- **ホストA/B/C**: 本設計上の役割名(物理マシン数とは独立)
- **窓 (window)**: 時系列を一定時間で区切った単位。本設計では1秒
