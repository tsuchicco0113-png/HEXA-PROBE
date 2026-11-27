// =====================================================================
//  HEXA STAGE  CPZ ｹｰｽ v0.1 — 本体＋USB-C PWR 基板＋CIO SMARTCOBY SLIM 5000mAh を全部包む外装
//  - 正面から見て本体のまわりに 12mm の枠 (上下左右同じ)。2分割:
//      A = 前ﾌﾚｰﾑ (本体と上の基板が入る。正面の縁が本体を押さえる)
//      B = 後ろｹｰｽ (ﾓﾊﾞﾌﾞが入る。背面に残量窓)
//    A と B は四隅の M2 ねじ (B の背面から、A の M2 ｲﾝｻｰﾄへ) で留める。ﾓﾊﾞﾌﾞが本体を前へ押し、
//    本体は正面の縁とﾓﾊﾞﾌﾞにはさまれる (本体へのねじ留めなし)
//  - 上の基板は天井の中に隠れる。天面には IR の窓だけ
//  - 左右の側面: 本体のﾎﾟｰﾄ (左 USB-A/USB-C/LAN、右 USB-C/Grove/音声/HDMI) が見える大きな窓
//  - ﾓﾊﾞﾌﾞ: 差し込み口側を正面から見て左に。ｹｰﾌﾞﾙは左端のすき間 (10mm) → 上の通り道 → 基板の USB-C
//    もう1つの USB-C は左の側面の穴から挿せる (充電・ﾊﾟｽｽﾙｰ)。電源ﾎﾞﾀﾝは底面の板ﾊﾞﾈで押す
//
//  座標: x = 正面から見て左→右 (本体 0〜84)、y = 正面から背面へ (本体の背面 0、正面 -22.1)、
//        z = 下→上 (本体 0〜54)。A/B の合わせ目は y = 0 (本体の背面)
//  印刷: A は正面を下、B は背面を下 (part="print_a" / "print_b")。どちらもｻﾎﾟｰﾄなし
// =====================================================================
part = "model";      // "model" / "print_a" / "print_b" / "fit" (fit は ../cap/body.stl が要る) / "explode"
$fn = 40;
eps = 0.01;

// ---- 本体 (公式 STL)
BW = 84.0;  BH = 54.0;  BD = 22.1;         // ｷｰを除いた奥行き (ｷｰ込み 23.1)
c  = 0.25;                                 // 本体とのすき間
// ---- 外形
m     = 12.0;                              // 枠の幅 (上下左右)
t     = 1.6;                               // 壁
lip_t = 1.2;                               // 正面の縁の厚み (本体の正面にかぶる)
lip   = [0.8, 1.5];                        // 縁が本体の正面にかぶる幅 [左右, 上下] (ｷｰの穴は端から 1.2〜)
front = -(BD + lip_t);                     // ｹｰｽの正面 (y)
R_out = 5.0;                               // 外の角の丸み
// ---- ﾓﾊﾞｲﾙﾊﾞｯﾃﾘｰ (実測 88×61、厚み 12.1)
LB = 88.0;  HB = 61.0;  TB = 12.1;
bfit = 0.4;
bay  = 10.0;                               // 差し込み口側 (左) の L 字ﾌﾟﾗｸﾞとｹｰﾌﾞﾙのすき間
bat_z0 = -5.4;                             // ﾓﾊﾞﾌﾞの下面 (下の四隅のねじの柱をよける)
bat_y0 = 0.2;                              // ﾓﾊﾞﾌﾞの前面 (本体の背面からのすき間)
// ﾓﾊﾞﾌﾞの各部 (差し込み口側の端・ﾎﾞﾀﾝ側の長辺からの寸法。★は未実測の仮の値)
btn_x   = 18.75;                           // ﾎﾞﾀﾝ中心 (端から。奥の縁 22mm の実測から)
port_b  = [40.0, 9.0, 3.6];                // ★ 外から挿す USB-C: 中心の高さ (ﾎﾞﾀﾝ側の長辺から), 幅, 厚み
disp    = [4.0, 19.0, 7.0, 17.0];          // ★ 残量表示の窓: 端から x0〜x1, ﾎﾞﾀﾝ側の長辺から z0〜z1
// ---- 後ろｹｰｽ
back_t = 2.0;                              // 背面の板
Bdep   = bat_y0 + TB + 0.3 + back_t;       // B の奥行き (14.6)
// ---- 上の基板 (USB-C PWR v0.2)
bx = 31.0;  PW = 22.0;  PD = 17.6;  brd_top = BH + 2.5 + 1.6;   // 基板の上面 (z)
press_gap = 0.15;
ir = [5.4, 14.4, 16.8, 20.2];              // IR の窓 (x0, x1, 背面からの奥行き y0, y1)
// ---- ねじ (M2 ｲﾝｻｰﾄ)
ins_d = 3.2;  ins_h = 5.5;                 // ｲﾝｻｰﾄの穴 (持っているｲﾝｻｰﾄに合わせる)
scr_d = 2.4;  head_d = 4.2;
screw_len = 16;                            // 使うねじの長さ → 頭の沈め深さが決まる
col_r = 2.9;

X0 = -m;  X1 = BW + m;  Z0 = -m;  Z1 = BH + m;
iX0 = X0 + t;  iX1 = X1 - t;  iZ0 = Z0 + t;  iZ1 = Z1 - t;
cols = [[X0 + 3.8, Z0 + 3.8], [X1 - 3.8, Z0 + 3.8], [X0 + 3.8, Z1 - 3.8], [X1 - 3.8, Z1 - 3.8]];
bat_x0 = iX0 + bay;  bat_x1 = bat_x0 + LB + 2*bfit;
bat_z1 = bat_z0 + HB + 2*bfit;

// 角を丸めた箱 (x-z の角を丸め、y 方向に伸ばす)
module rbox(x0, x1, z0, z1, y0, y1, r) {
  hull() for (x = [x0 + r, x1 - r], z = [z0 + r, z1 - r])
    translate([x, y1, z]) rotate([90, 0, 0]) cylinder(r = r, h = y1 - y0);
}
// y-z 面の角丸の穴 (x 方向に抜く)
module yz_hole(y0, y1, z0, z1, r, xa, xb) {
  hull() for (y = [y0 + r, y1 - r], z = [z0 + r, z1 - r])
    translate([xa, y, z]) rotate([0, 90, 0]) cylinder(r = r, h = xb - xa);
}
// x-y 面の角丸の穴 (z 方向に抜く)
module xy_hole(x0, x1, y0, y1, r, za, zb) {
  hull() for (x = [x0 + r, x1 - r], y = [y0 + r, y1 - r]) translate([x, y, za]) cylinder(r = r, h = zb - za);
}

// ---------------- A: 前ﾌﾚｰﾑ ----------------
module part_a() {
  difference() {
    union() {
      difference() {
        rbox(X0, X1, Z0, Z1, front, 0, R_out);
        // 中 (正面の板 2mm を残す)
        rbox(iX0, iX1, iZ0, iZ1, front + 2.0, eps, R_out - t);
        // 本体の正面の窓 (縁 lip だけかぶる)
        rbox(lip[0], BW - lip[0], lip[1], BH - lip[1], front - 1, 0, 2);
        // 本体の入る所 (正面の板の中まで)
        rbox(-c, BW + c, -c, BH + c, -BD - c, 1, 2.5);
      }
      // 四隅の柱 (ｲﾝｻｰﾄ)
      for (p = cols) translate([p[0], 0, p[1]]) rotate([90, 0, 0]) cylinder(r = col_r, h = -front - 1);
      // 本体の位置決めﾘﾌﾞ (すべて y 方向に伸びる板 = 正面を下に刷ると縦)
      rib_y = [front + 1.5, 0];
      for (zz = [[0.4, 1.6], [BH - 1.6, BH - 0.4]]) {                 // 左右 (窓の上下の外)
        translate([iX0 - eps, rib_y[0], zz[0]]) cube([-c - iX0 + eps, rib_y[1] - rib_y[0], zz[1] - zz[0]]);
        translate([BW + c, rib_y[0], zz[0]]) cube([iX1 - BW - c + eps, rib_y[1] - rib_y[0], zz[1] - zz[0]]);
      }
      for (x = [8, 74.4]) translate([x, rib_y[0], iZ0 - eps]) cube([1.6, rib_y[1] - rib_y[0], -c - iZ0 + eps]);   // 下
      for (x = [21, 61.4]) translate([x, rib_y[0], BH + c]) cube([1.6, rib_y[1] - rib_y[0], iZ1 - BH - c + eps]); // 上
      // 基板の押さえ (LEGO 穴の横、USB-C をよける)
      for (x = [33.0, 48.8]) translate([x, rib_y[0], brd_top + press_gap]) cube([2.2, rib_y[1] - rib_y[0], iZ1 - brd_top - press_gap + eps]);
    }
    // ｲﾝｻｰﾄの穴
    for (p = cols) translate([p[0], 1, p[1]]) rotate([90, 0, 0]) cylinder(d = ins_d, h = ins_h + 1);
    // 左右の窓 (合わせ目まで開く → 正面を下に刷っても橋にならない)
    for (xs = [[X0 - 1, iX0 + eps], [iX1 - eps, X1 + 1]]) yz_hole(-21.0, 3.0, 2.0, 52.0, 2.0, xs[0], xs[1]);
    // IR の窓
    xy_hole(ir[0] - 0.5, ir[1] + 0.5, -ir[3] - 0.5, -ir[2] + 0.5, 1.2, iZ1 - 1, Z1 + 1);
    // 底のｽﾋﾟｰｶｰの穴 (本体の底の穴の下)
    for (i = [0 : 8]) translate([33.4 + i * 2.4, -16.0, Z0 - 1]) hull() {
      translate([0.6, 0, 0]) cylinder(d = 1.2, h = t + 2);
      translate([0.6, 5.0, 0]) cylinder(d = 1.2, h = t + 2);
    }
  }
}

// ---------------- B: 後ろｹｰｽ ----------------
module part_b() {
  head_sink = Bdep - (screw_len - (ins_h - 1.0));    // ねじ頭の沈め (ねじが ｲﾝｻｰﾄに ins_h-1 入る)
  difference() {
    union() {
      difference() {
        rbox(X0, X1, Z0, Z1, 0, Bdep, R_out);
        rbox(iX0, iX1, iZ0, iZ1, -eps, Bdep - back_t, R_out - t);
      }
      // A に入る位置決めの縁 (内周、1.5mm)
      difference() {
        union() {
          rbox(iX0 + 0.15, iX1 - 0.15, iZ0 + 0.15, iZ1 - 0.15, -1.5, 0.1, R_out - t - 0.15);
          rbox(iX0 - 0.5, iX1 + 0.5, iZ0 - 0.5, iZ1 + 0.5, -eps, 1.0, R_out - t);     // B の壁とつなぐ
        }
        rbox(iX0 + 1.35, iX1 - 1.35, iZ0 + 1.35, iZ1 - 1.35, -2, 1.1, R_out - t - 1.35);
        for (p = cols) translate([p[0], 1, p[1]]) rotate([90, 0, 0]) cylinder(r = col_r + 0.3, h = 3);
        // 左右の窓の所は縁を切る (窓から見えないように)
        for (xs = [[X0 - 1, iX0 + 2], [iX1 - 2, X1 + 1]]) yz_hole(-3, 0.5, 2.0, 52.0, 0.5, xs[0], xs[1]);
      }
      // 四隅の柱
      for (p = cols) translate([p[0], Bdep - eps, p[1]]) rotate([90, 0, 0]) cylinder(r = col_r, h = Bdep);
      // ﾓﾊﾞﾌﾞの受け (下)、右端の止め、上の止め、左 (差し込み口側) の止め — どれも y 方向の板
      by = [bat_y0 + 0.3, Bdep - back_t + eps];
      for (x = [bat_x0 + 10, (bat_x0 + bat_x1)/2 + 6, bat_x1 - 12]) translate([x, by[0], iZ0 - eps]) cube([1.6, by[1] - by[0], bat_z0 - iZ0 + eps]);
      translate([bat_x1, by[0], bat_z0 + 8]) cube([iX1 - bat_x1 + eps, by[1] - by[0], HB - 16]);
      for (x = [bat_x0 + 6, bat_x1 - 14]) translate([x, by[0], bat_z1]) cube([1.6, by[1] - by[0], 1.6]);
      for (zz = [[bat_z0, bat_z0 + 4], [bat_z1 - 4, bat_z1]]) translate([bat_x0 - 1.6, by[0], zz[0]]) cube([1.6, by[1] - by[0], zz[1] - zz[0]]);
      // 電源ﾎﾞﾀﾝの板ﾊﾞﾈの押し棒 (下の壁の舌から上へ、下側は斜め)
      translate([bat_x0 + btn_x, 0, 0]) hull() {
        translate([-2, bat_y0 + TB/2 - 2, iZ0 - eps]) cube([4, 4, bat_z0 - 0.25 - iZ0]);
        translate([-2, Bdep - back_t - 1.6 - 4, iZ0 - eps]) cube([4, 1, 0.5]);
      }
    }
    // ねじ穴 (背面から)
    for (p = cols) translate([p[0], Bdep + 1, p[1]]) rotate([90, 0, 0]) {
      cylinder(d = scr_d, h = Bdep + 2);
      cylinder(d = head_d, h = 1 + max(head_sink, 0.4));
    }
    // 板ﾊﾞﾈ (下の壁を コ の字に切る。根元は背面側)
    translate([bat_x0 + btn_x, 0, Z0 - 1]) difference() {
      translate([-5, 1.0, 0]) cube([10, Bdep - back_t - 1.6 - 1.0, t + 1 + eps]);
      translate([-4.2, 1.8, -1]) cube([8.4, Bdep - back_t - 1.6, t + 3]);
    }
    // 外から挿す USB-C (左の側面)
    yz_hole(bat_y0 + TB/2 - port_b[2]/2 - 2.0, bat_y0 + TB/2 + port_b[2]/2 + 2.0,
            bat_z0 + bfit + port_b[0] - port_b[1]/2 - 2.0, bat_z0 + bfit + port_b[0] + port_b[1]/2 + 2.0, 2.5, X0 - 1, iX0 + eps);
    // 残量窓 (背面)
    xy_hole_y(bat_x0 + bfit + disp[0], bat_x0 + bfit + disp[1], bat_z0 + bfit + disp[2], bat_z0 + bfit + disp[3], 1.5);
  }
}
module xy_hole_y(x0, x1, z0, z1, r) {
  hull() for (x = [x0 + r, x1 - r], z = [z0 + r, z1 - r]) translate([x, Bdep + 1, z]) rotate([90, 0, 0]) cylinder(r = r, h = back_t + 2);
}

// ---------------- 確認用 ----------------
module body() {
  // 公式 STL (x 0〜84 / y 5〜59 = 高さ / z 0〜23.1 = 背面→正面) → (x, -z, y-5)
  multmatrix([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, -5], [0, 0, 0, 1]]) import("../cap/body.stl");
}
module battery() {
  color([0.1, 0.1, 0.11]) translate([bat_x0 + bfit, bat_y0, bat_z0 + bfit])
    hull() for (x = [4, LB - 4], z = [4, HB - 4]) translate([x, 0, z]) rotate([-90, 0, 0]) cylinder(r = 4, h = TB);
}
module board() { color([0.1, 0.1, 0.1]) translate([bx, -PD, BH + 2.5]) cube([PW, PD, 1.6]); }

if (part == "print_a") rotate([90, 0, 0]) translate([0, -front, 0]) part_a();          // 正面を下
else if (part == "print_b") rotate([-90, 0, 0]) translate([0, -Bdep, 0]) part_b();       // 背面を下
else if (part == "fit") { color([0.45, 0.47, 0.5]) body(); board(); battery();
                          color([0.16, 0.16, 0.17], 0.55) part_a(); color([0.2, 0.2, 0.21], 0.55) part_b(); }
else if (part == "explode") { color([0.45, 0.47, 0.5]) body(); battery();
                          color([0.18, 0.18, 0.19]) translate([0, -25, 0]) part_a(); color([0.18, 0.18, 0.19]) translate([0, 25, 0]) part_b(); }
else if (part == "none") ;
else if (part == "show") { color([0.45, 0.47, 0.5]) body(); color([0.13, 0.13, 0.14]) part_a(); color([0.15, 0.15, 0.16]) part_b(); }
else if (part == "a") part_a();
else if (part == "b") part_b();
else { color([0.18, 0.18, 0.19]) part_a(); color([0.2, 0.2, 0.21]) part_b(); }
