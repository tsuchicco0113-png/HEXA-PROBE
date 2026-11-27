// =====================================================================
//  HEXA STAGE  CPZ 背面バッテリーﾄﾚｲ v0.1  (CIO SMARTCOBY SLIM 5000mAh 用)
//  CPZ の背面に M2 ﾈｼﾞ2本で付けるﾄﾚｲ。ﾊﾞｯﾃﾘｰはﾎﾟｰﾄ側の端から横に差し込む。
//  ｶﾒﾗは隠れる (了承済み)。上の USB-C ｷｬｯﾌﾟと短い C-C ｹｰﾌﾞﾙでつなぐ。
//
//  座標: 背面を正面に見て u = 左→右 (x)、v = 下→上 (y、本体の下端 0)、
//        w = 背面から外向き (z、背面 0)。このまま印刷 (背面に当たる面が下)
// =====================================================================
part = "print";        // "print" / "fit"
$fn = 40;
eps = 0.01;

// ---- 本体 (CPZ の背面、公式 外形図より)
BW = 84.0;  BH = 54.0;
inserts = [[14, 40], [71, 30]];        // 背面の M2 ｲﾝｻｰﾄ (背面から見て)
camera  = [42, 47.7];
// 上のｷｬｯﾌﾟの耳 (M2) が背面上端に来る所。ここは床を抜いて、ﾈｼﾞ頭はﾊﾞｯﾃﾘｰの下に入れる
cap_ears = [[28, 50.9], [56, 50.9]];   // ｷｬｯﾌﾟの耳ﾈｼﾞ (背面から見ても左右対称)

// ---- ﾊﾞｯﾃﾘｰ (価格.com の仕様: 60.8 x 88 x 12.11)
LB = 88.0;  HB = 60.8;  TB = 12.11;
fit = 0.4;                             // 片側のすき間 (PETG の縮みも見て 0.4)
PL = LB + 2*fit;  PH = HB + 2*fit;  PT = TB + 0.3;

// ---- ﾄﾚｲ
floor_t = 4.0;          // 背面からﾊﾞｯﾃﾘｰまで (耳ﾈｼﾞの頭 約3.9mm を逃がす)
wall    = 1.6;
lip     = 1.6;          // ﾊﾞｯﾃﾘｰの表面にかぶさる縁の幅 (長辺だけ。表示は隠さない)
lip_t   = 1.4;
open_end = "right";     // ﾎﾟｰﾄ側 = 差し込み口。背面から見て "right" / "left"
pocket_top = 55.0;      // ﾎﾟｹｯﾄ上端 (v)。ｷｬｯﾌﾟの USB-C ﾌﾟﾗｸﾞ (下端 約56.2) に当たらない高さ
plug_notch = [33, 51];  // 上の壁をﾌﾟﾗｸﾞの分だけ切る (u の範囲)
button_cut = 18;        // 差し込み口側の長辺の壁を切る長さ (横のﾎﾞﾀﾝを押せるように、上下両方)
snap = 0.5;             // 差し込み口の抜け止めの出っ張り

pu0 = BW/2 - PL/2;  pu1 = BW/2 + PL/2;         // ﾎﾟｹｯﾄ (u)
pv1 = pocket_top;   pv0 = pv1 - PH;            // ﾎﾟｹｯﾄ (v)
pw0 = floor_t;      pw1 = floor_t + PT;        // ﾎﾟｹｯﾄ (w)
H   = pw1 + lip_t;

ou0 = pu0 - wall;  ou1 = pu1 + wall;
ov0 = pv0 - wall;  ov1 = pv1 + wall;

module rbox(x0, x1, y0, y1, z0, z1, r) {
  translate([0, 0, z0]) hull() for (x = [x0 + r, x1 - r], y = [y0 + r, y1 - r])
    translate([x, y, 0]) cylinder(r = r, h = z1 - z0);
}

module tray() {
  difference() {
    rbox(ou0, ou1, ov0, ov1, 0, H, 3);
    // ﾊﾞｯﾃﾘｰのﾎﾟｹｯﾄ (差し込み口側は端まで抜く)
    xo0 = open_end == "left"  ? ou0 - 1 : pu0;
    xo1 = open_end == "right" ? ou1 + 1 : pu1;
    translate([xo0, pv0, pw0]) cube([xo1 - xo0, PH, PT]);
    // 表側: 長辺の縁 (lip) だけ残して開ける (残量表示が見える)
    translate([xo0, pv0 + lip, pw1 - eps]) cube([xo1 - xo0, PH - 2*lip, lip_t + 1]);
    // 上の壁の切り欠き (ｷｬｯﾌﾟの USB-C ﾌﾟﾗｸﾞ)
    translate([plug_notch[0], pv1 - lip - 0.05, pw0 + 1.5]) cube([plug_notch[1] - plug_notch[0], wall + lip + 1, H]);
    // ﾎﾞﾀﾝ用: 差し込み口側の長辺の壁 (上下とも)
    bu0 = open_end == "right" ? pu1 - button_cut : ou0 - 1;
    bu1 = open_end == "right" ? ou1 + 1 : pu0 + button_cut;
    for (vv = [[ov0 - 1, pv0 + lip + 0.05], [pv1 - lip - 0.05, ov1 + 1]])   // 縁ごと切る (浮いた縁を残さない)
      translate([bu0, vv[0], pw0 + 1.5]) cube([bu1 - bu0, vv[1] - vv[0], H]);
    // 床: 本体の M2 ｲﾝｻｰﾄへのﾈｼﾞ (ﾊﾞｯﾃﾘｰ側から皿もみ、ﾈｼﾞ下の床 1.5mm)
    for (p = inserts) translate([p[0], p[1], -eps]) {
      cylinder(d = 2.3, h = floor_t + 1);
      translate([0, 0, 1.5]) cylinder(d = 4.3, h = floor_t);
    }
    // 床: ｷｬｯﾌﾟの耳とﾈｼﾞ頭の逃げ
    for (p = cap_ears) translate([p[0] - 4.6, p[1] - 4, -eps]) cube([9.2, 20, floor_t + eps]);
    // 床: ｶﾒﾗの逃げ (ﾚﾝｽﾞが少し出ていても当たらないように)
    translate([camera[0], camera[1], -eps]) cylinder(d = 9, h = floor_t + eps);
    // 床の肉抜き (軽く、熱がこもらないように) — ﾈｼﾞの周りは残す
    for (u = [12, 28, 42, 56, 72]) for (v = [8, 22])
      if (norm([u - inserts[0][0], v - inserts[0][1]]) > 9 && norm([u - inserts[1][0], v - inserts[1][1]]) > 9)
        translate([u, v, -eps]) cylinder(d = 8, h = floor_t + eps, $fn = 6);
  }
  // 縁の下の 45° のﾘﾌﾞ (長辺の縁を支える)
  for (side = [0, 1]) {
    y = side == 0 ? pv0 : pv1;
    s = side == 0 ? 1 : -1;
    lu0 = open_end == "right" ? pu0 : pu0 + button_cut;
    lu1 = open_end == "right" ? pu1 - button_cut : pu1;
    translate([lu0, y, pw1]) rotate([0, 90, 0]) linear_extrude(lu1 - lu0)
      polygon([[0, 0], [0, s * 0.01], [0.01, 0]]);   // (形だけ。縁 1.6 は 45° 以内なので支え不要)
  }
  // 差し込み口の抜け止め (ﾎﾟｹｯﾄの床に小さな山。ﾊﾞｯﾃﾘｰを押し込むと乗り越える)
  // 山はﾊﾞｯﾃﾘｰが奥まで入った時の端より外 (ﾎﾟｹｯﾄの外の床) に置く。中に置くとﾊﾞｯﾃﾘｰが乗り上げて入りきらない
  su = open_end == "right" ? pu1 + 0.7 : pu0 - 0.7;
  for (v = [pv0 + 12, pv1 - 12]) translate([su, v, pw0 - 0.15]) scale([1, 4, 1]) sphere(r = snap + 0.15, $fn = 16);
}

module dummy() {
  color([0.55, 0.57, 0.6]) translate([0, 0, -22.1]) cube([BW, BH, 22.1]);
  color([0.12, 0.12, 0.13]) translate([BW/2 - LB/2, pv1 - fit - HB, pw0]) cube([LB, HB, TB]);
  // ｷｬｯﾌﾟの USB-C ﾌﾟﾗｸﾞ (目安)
  color("dimgray") translate([42 - 6.3, BH + 2.2, 0.3]) cube([12.6, 7, 22]);
}

if (part == "print") tray();
else { dummy(); color("whitesmoke", 0.9) tray(); }
