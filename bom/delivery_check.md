# Delivery check: remaining purchases to BU (ZIP 02215)

> **Servo change, 2026-10-14:** the yeast auger is now driven by the owned Feetech FB5311M-360 (BOM `ELE-40`). The rows for the N20 gearmotor 3-pack (`ELE-11`), the encoder N20 (`ELE-10`), the TB6612FNG (`ELE-09`), the N20 M1.6 screws (`FAS-15`) and the 1 A fuse (`ELE-20`) are `dropped` in `bom/BOM.csv`: do not order them. The auger now has its own 3 A branch fuse (`ELE-42`), covered by the 20-pack of 3 A fuses listed under `ELE-19`; its 25T horn comes from the Treedix 10-pack (`ELE-31`). `ELE-25` needs only 10 k x2 and `ELE-33` only 100 nF x1 (the STBY pull-down and the N20 caps are gone), so both kits are still needed but for less. `CON-20` is kept for the auger servo lead. The table below is the record of the 13:15 check and still lists `ELE-20` as ORDER: skip it.

**Checked:** Wed 2026-10-14, 13:15-13:21 EDT (browser clock 12:15-12:21 CDT), amazon.com, not signed in, Deliver to: Boston 02215. Delivery dates change hourly, so re-check before ordering.

**Deadline:** in hand by Fri Oct 16 morning (team arrives Thu Oct 15 evening). Changes already applied: N20 gearmotor, encoder N20 and TB6612 dropped (auger is the Feetech FB5311M-360); ISO 7380 M4x20 included; arm adapters skipped (voltage unconfirmed). Status `buy-in-Boston` rows excluded.

**Summary:** 80 purchase lines: **76 arrive Thu Oct 15**, **4 arrive Fri Oct 16** (date only, not guaranteed morning), **1 cannot be bought on Amazon** (ELE-36, LOCAL), 1 LOCAL/confirm (LAB-04), 1 skipped pending info (ELE-37). **Total $1,087.49** before tax (Thu $1,000.12 + Fri $87.37).

> **Every Thu/Fri date needs Prime.** Without Prime, every item showed Mon Oct 19.

| BOM id | item | qty | Amazon link (ASIN) | price | earliest delivery to 02215 | arrives in time? | action |
|---|---|---|---|---|---|---|---|
| GLS-01 | Karter 250 mL Erlenmeyer flask | 2 | [B006VYY10Y](https://www.amazon.com/dp/B006VYY10Y) | $8.20 x2 = $16.40 | Thu Oct 15 (Prime) | YES | ORDER. 1 + 1 spare. Confirm with ordering teammate (README Oct 13 list). |
| GLS-02 | Glass stir rods 6.35 x 150, pack of 4 | 1 | [B099QK8PX8](https://www.amazon.com/dp/B099QK8PX8) | $6.99 | Thu Oct 15 (Prime) | YES | ORDER |
| GLS-03 | 100 mL borosilicate graduated cylinder (Karter) | 1 | [B006UKIASI](https://www.amazon.com/dp/B006UKIASI) | $10.99 | Thu Oct 15 (Prime) | YES | ORDER. Search pick. |
| LAB-01 | EISCO 50 mL PP beaker (single per listing) | 6 | [B00BHLE5AW](https://www.amazon.com/dp/B00BHLE5AW) | $9.19 x6 = $55.14 | Fri Oct 16 (Prime, date only) | FRI-AM | ORDER (Fri). Listing is ONE beaker ($9.19 each), so 6 units needed. No Thursday listing matching EISCO 50 mL PP found. Fri delivery may come any time up to ~10 PM. |
| LAB-02 | EISCO 100 mL PP beaker, 12-pack | 1 | [B00BHLE5RU](https://www.amazon.com/dp/B00BHLE5RU) | $16.29 | Fri Oct 16 (Prime, date only) | FRI-AM | ORDER (Fri). Covers 5 needed. Fri only. |
| LAB-03 | EISCO 4 in PP funnel | 1 | [B017UYYKSQ](https://www.amazon.com/dp/B017UYYKSQ) | $9.99 | Thu Oct 15 (Prime) | YES | ORDER |
| LAB-04 | PP bin ~110 x 80 x 100 (waste/rinse) | 0 | - | - | - | LOCAL | CONFIRM USE; buy at CVS/Target if needed. Provisional, purpose undocumented in BOM. No Amazon listing found matching 110x80x100; any small plastic tub from CVS/Target near Kenmore works. |
| LAB-05 | Clear PP overflow container (optional) | 0 | - | - | - | SKIP | Optional, qty 0. Optional per CDR-19. Amazon options found were 6 in (152 mm) OD > 150 mm limit. Skip. |
| FAS-01 | SHCS M3x20 | 0 | [B0FG2BRXL3](https://www.amazon.com/dp/B0FG2BRXL3) | - | Thu Oct 15 (Prime) | YES | Covered by FAS-05 kit. Kit has 20 mm. |
| FAS-02 | ISO 7380 M4x20 button head, 50 pcs (Fullerkreg) | 1 | [B07H17FG9R](https://www.amazon.com/dp/B07H17FG9R) | $8.89 | Thu Oct 15 (Prime) | YES | ORDER. Search pick. Needed (CDR-11). |
| FAS-03 | SHCS M4x20 12.9 (arm back row) | 1 | [B0CHJDMJ3H](https://www.amazon.com/dp/B0CHJDMJ3H) | $8.99 | Thu Oct 15 (Prime) | YES | ORDER replacement kit. BOM link B017NENNVS has NO buy box (no price/delivery offered). Replaced by mxuteuk M4 12.9 kit M4x6/8/12/16/20/30 (also covers FAS-14). |
| FAS-04 | 2020 M4 drop-in T-nut, 100 pcs (HELIFOUNER) | 1 | [B0B1LTL6M5](https://www.amazon.com/dp/B0B1LTL6M5) | $5.99 | Thu Oct 15 (Prime) | YES | ORDER replacement. BOM link B0DJG8FFGS delivers Oct 26-Nov 4 (NO); BOM alt B09FSJXB15 delivers Wed Oct 21 (NO). Replaced. |
| FAS-05 | M3 SHCS kit 720 pcs M3x6-30 (+washers) | 1 | [B0FG2BRXL3](https://www.amazon.com/dp/B0FG2BRXL3) | $9.99 | Thu Oct 15 (Prime) | YES | ORDER. Covers FAS-01/05/07/17. |
| FAS-06 | Servo ear screws | 0 | - | - | - | YES | Supplied with servos. Come with FlashHobby M45CHW. |
| FAS-07 | SHCS M3x16 | 0 | [B0FG2BRXL3](https://www.amazon.com/dp/B0FG2BRXL3) | - | Thu Oct 15 (Prime) | YES | Covered by FAS-05 kit. Kit has 16 mm. |
| FAS-08 | DIN 985 M3 nylon locknut, 120 pcs | 1 | [B0FJ8QP76C](https://www.amazon.com/dp/B0FJ8QP76C) | $9.23 | Thu Oct 15 (Prime) | YES | ORDER. Search pick. |
| FAS-09 | M3x12 set screw (grub) | 1 | [B0DDHL6P99](https://www.amazon.com/dp/B0DDHL6P99) | $6.89 | Thu Oct 15 (Prime) | YES | ORDER. Low stock. Backup: B0CZ6X8T4C ($5.99, Fri) or Ace/Home Depot. |
| FAS-10 | SHCS M5x12 | 0 | [B0DMCS8KW4](https://www.amazon.com/dp/B0DMCS8KW4) | - | Thu Oct 15 (Prime) | YES | Covered by FAS-13 pack |
| FAS-11 | M5 SHCS kit 272 pcs M5x8-35 | 1 | [B0FGV561HZ](https://www.amazon.com/dp/B0FGV561HZ) | $9.99 | Thu Oct 15 (Prime) | YES | ORDER |
| FAS-12 | SHCS M5x8 | 0 | [B0DMCS8KW4](https://www.amazon.com/dp/B0DMCS8KW4) | - | Thu Oct 15 (Prime) | YES | Covered by FAS-13 pack |
| FAS-13 | 2020 M5 T-nut + M5 screw kit, 240 pcs | 1 | [B0DMCS8KW4](https://www.amazon.com/dp/B0DMCS8KW4) | $12.99 | Thu Oct 15 (Prime) | YES | ORDER. Covers FAS-10/12. |
| FAS-14 | SHCS M4x12 | 0 | [B0CHJDMJ3H](https://www.amazon.com/dp/B0CHJDMJ3H) | - | Thu Oct 15 (Prime) | YES | Covered by FAS-03 kit. BOM link B074TFLBFQ delivers Oct 26-Nov 3 (NO). Use the M4 kit instead. |
| FAS-15 | M1.6x4 screws for N20 | 0 | - | - | - | SKIP | Not needed. N20 dropped (auger is now Feetech FB5311M-360). |
| FAS-16 | ruthex M5 heat-set inserts, 50 | 1 | [B07YSVXWS8](https://www.amazon.com/dp/B07YSVXWS8) | $9.99 | Thu Oct 15 (Prime) | YES | ORDER |
| FAS-17 | M3 washers | 0 | [B0FG2BRXL3](https://www.amazon.com/dp/B0FG2BRXL3) | - | Thu Oct 15 (Prime) | YES | Covered by FAS-05 kit |
| FAS-18 | M3 brass standoff kit, 120 pcs | 1 | [B06XQ33Y9X](https://www.amazon.com/dp/B06XQ33Y9X) | $8.99 | Thu Oct 15 (Prime) | YES | ORDER. Search pick. |
| HDW-01 | F625ZZ flanged bearing, 10 pcs | 1 | [B0G1B256ZS](https://www.amazon.com/dp/B0G1B256ZS) | $8.49 | Thu Oct 15 (Prime) | YES | ORDER. Low stock. |
| HDW-04 | BESSEY CM34DR C-clamp, 2-pack | 1 | [B0CBZ9J74Y](https://www.amazon.com/dp/B0CBZ9J74Y) | $19.06 | Thu Oct 15 (Prime) | YES | ORDER |
| HDW-07 | ABS project box 200x120x75 (IP65) | 1 | [B06XSQZ5M6](https://www.amazon.com/dp/B06XSQZ5M6) | $9.99 | Thu Oct 15 (Prime) | YES | ORDER. Inner 193x113x68. CAD envelope is 200x90x60: box is 120 wide x 75 tall, check plan3 scene. |
| ELE-02 | 2S LiPo balance charger, AC input, XT60 (OVONIC Mate1) | 1 | [B0G6CV6BNR](https://www.amazon.com/dp/B0G6CV6BNR) | $50.99 | Thu Oct 15 (Prime) | YES | ORDER (skip if pack has charger). 100-240 V AC input, 2S-6S LiPo. Set LiPo mode, never LiHV. |
| ELE-03 | LiPo safe bag (Zeee) | 1 | [B07KZQZBN2](https://www.amazon.com/dp/B07KZQZBN2) | $13.49 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-04 | LiPo cell checker/alarm 1-8S | 1 | [B013U1CP08](https://www.amazon.com/dp/B013U1CP08) | $5.99 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-05 | Sabrent 4-port powered USB 3.0 hub (HB-UMP3) | 1 | [B00TPMEOYM](https://www.amazon.com/dp/B00TPMEOYM) | $19.99 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-07 | USB-A to micro-USB data cable, 2-pack | 1 | [B0719H12WD](https://www.amazon.com/dp/B0719H12WD) | $7.25 | Thu Oct 15 (Prime) | YES | ORDER. Mega 2560 PRO (Embed) listings use micro-USB. Still inspect the board. |
| ELE-08 | ShangHJ 1 kg load cell + HX711, 2 sets | 1 | [B09K7G51KJ](https://www.amazon.com/dp/B09K7G51KJ) | $9.99 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-09 | TB6612FNG driver | 0 | [B08J3S6G2N](https://www.amazon.com/dp/B08J3S6G2N) | - | - | SKIP | Not needed. Dropped: auger is now Feetech FB5311M-360. |
| ELE-10 | N20 gearmotor with encoder | 0 | - | - | - | SKIP | Not needed. Dropped. |
| ELE-11 | N20 gearmotor, plain (already ordered) | 0 | [B0F83T7531](https://www.amazon.com/dp/B0F83T7531) | - | - | SKIP | Already bought, now unused. Dropped. |
| ELE-12 | 20 AWG twisted JR servo ext. w/ clip, 120 cm, 5-pack (BackBayRC) | 1 | [B0CXR2YBS4](https://www.amazon.com/dp/B0CXR2YBS4) | $24.49 | Thu Oct 15 (Prime) | YES | ORDER. No 1.0 m variant in this family; 120 cm is the closest above 1 m. 5-pack covers 1 + 1 spare. |
| ELE-13 | 20 AWG twisted JR servo ext. w/ clip, 30 cm, 5-pack (BackBayRC) | 1 | [B0CXQ8RZH8](https://www.amazon.com/dp/B0CXQ8RZH8) | $14.49 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-14 | 16 AWG silicone wire, 10 ft red + 10 ft black | 1 | [B0D93K21TN](https://www.amazon.com/dp/B0D93K21TN) | $7.99 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-15 | 20 AWG silicone wire, 10 ft red + 10 ft black (BNTECHGO) | 1 | [B01AAX64EC](https://www.amazon.com/dp/B01AAX64EC) | $8.48 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-16 | 22 AWG stranded hook-up wire, 6 colours | 1 | [B089CQHRDT](https://www.amazon.com/dp/B089CQHRDT) | $12.79 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-17 | WAGO 221 12-pc kit (3x 221-415, 3x 413, 3x 412, 3x 2401) | 1 | [B0CJ5QF4Z2](https://www.amazon.com/dp/B0CJ5QF4Z2) | $12.45 | Thu Oct 15 (Prime) | YES | ORDER + buy 1 more 221-415 LOCAL. Need 4x 221-415; kit has 3. 4th: Home Depot / Micro Center. Alt: genuine 25-pk B0107SYYGU $22.03 arrives FRI only (cutoff ~15:50 EDT). |
| ELE-18 | Inline ATO fuse holder 16 AWG, 4-pack (+20 fuses) | 1 | [B0F6NPV287](https://www.amazon.com/dp/B0F6NPV287) | $7.99 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-19 | ATO blade fuse 3 A, 20 pcs | 1 | [B0DHS1GTC7](https://www.amazon.com/dp/B0DHS1GTC7) | $3.99 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-20 | ATO blade fuse 1 A, 25 pcs | 1 | [B0DSCF5H9J](https://www.amazon.com/dp/B0DSCF5H9J) | $4.99 | Thu Oct 15 (Prime) | YES | ORDER (confirm still needed). 1 A fuse was for the TB6612 VM, which is dropped. Re-purpose for the FB5311M feed or skip. |
| ELE-21 | ATO blade fuse 10 A, 25 pcs | 1 | [B0DSCGW488](https://www.amazon.com/dp/B0DSCGW488) | $4.99 | Thu Oct 15 (Prime) | YES | ORDER. Swap into ELE-22 (it ships with 30 A fuses). |
| ELE-22 | XT60 M-F lead with blade-fuse holder, 2 pcs | 1 | [B0BZ7Y1DQY](https://www.amazon.com/dp/B0BZ7Y1DQY) | $12.99 | Thu Oct 15 (Prime) | YES | ORDER. Ships with 30 A fuses; fit the 10 A (ELE-21). |
| ELE-23 | Taiss 22 mm e-stop 2NC latching, in station box | 1 | [B07GPF76R1](https://www.amazon.com/dp/B07GPF76R1) | $16.99 | Thu Oct 15 (Prime) | YES | ORDER FIRST (early cutoff). Thursday only if ordered within ~1 h 50 min of check (~15:05 EDT); after that Mon Oct 19. Box colour not stated (yellow not confirmed). |
| ELE-24 | HiLetgo 5 V 1-ch relay module, H/L trigger, 2 pcs | 1 | [B00LW15A4W](https://www.amazon.com/dp/B00LW15A4W) | $7.39 | Thu Oct 15 (Prime) | YES | ORDER. Check the relay is SRD-05VDC-SL-C on arrival. |
| ELE-25 | Metal film resistor kit 1/4 W 1%, 50 values | 1 | [B0CDWVLTM1](https://www.amazon.com/dp/B0CDWVLTM1) | $8.99 | Thu Oct 15 (Prime) | YES | ORDER. Confirm 33 k and 10 k values in kit. |
| ELE-26 | HiLetgo INA226 module, 2 pcs | 1 | [B0CDWXB8PG](https://www.amazon.com/dp/B0CDWXB8PG) | $10.99 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-27 | 2512 2 W R010 shunt resistor, 50 pcs | 1 | [B0FVM8PRL5](https://www.amazon.com/dp/B0FVM8PRL5) | $5.99 | Fri Oct 16 (Prime, date only) | FRI-AM | ORDER (Fri). No Thursday 2512 10 mOhm found. Fallback: use the INA226 board's onboard R100 shunt until it arrives. |
| ELE-28 | Rubycon 2200 uF 16 V low-ESR | 1 | [B0FVGBGMW2](https://www.amazon.com/dp/B0FVGBGMW2) | $6.99 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-29 | FlashHobby M45CHW 45 kg servo (carousel + stage) | 2 | [B09VBFZ9KW](https://www.amazon.com/dp/B09VBFZ9KW) | $44.99 x2 = $89.98 | Thu Oct 15 (Prime) | YES | ORDER (skip if 2 owned) |
| ELE-30 | FlashHobby M45CHW spare | 1 | [B09VBFZ9KW](https://www.amazon.com/dp/B09VBFZ9KW) | $44.99 | Thu Oct 15 (Prime) | YES | ORDER. Same listing as ELE-29: order qty 3 total. |
| ELE-31 | Treedix 25T Al disc horn, 10 pcs | 1 | [B0875ZS9KF](https://www.amazon.com/dp/B0875ZS9KF) | $8.99 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-32 | 470 uF 16 V electrolytic, 8x12 mm | 1 | [B0CMQCQMH5](https://www.amazon.com/dp/B0CMQCQMH5) | $5.99 | Thu Oct 15 (Prime) | YES | ORDER. Thursday listing is not marked low-ESR. Low-ESR option B0D78PQ4C1 (10-pk $4.99) arrives FRI only. |
| ELE-33 | Monolithic ceramic cap kit, 24 values (incl. 47 nF, 100 nF) | 1 | [B0C1V8Q93P](https://www.amazon.com/dp/B0C1V8Q93P) | $9.99 | Thu Oct 15 (Prime) | YES | ORDER. Title lists both 47 nF and 100 nF. |
| ELE-34 | A3144 Hall sensor, 20 pcs | 1 | [B0CZ6QXMZ2](https://www.amazon.com/dp/B0CZ6QXMZ2) | $6.99 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-35 | N52 6x2 mm magnets, 50 pcs | 1 | [B0H55FXL9W](https://www.amazon.com/dp/B0H55FXL9W) | $9.99 | Thu Oct 15 (Prime) | YES | ORDER |
| ELE-36 | Screw-terminal breakout for Mega 2560 PRO (Embed) | 0 | - | - | - | NO | LOCAL: Micro Center (perfboard + screw terminals) or skip. No Mega 2560 PRO-specific terminal shield found on Amazon; the listings are for the full-size Mega R3 footprint (wrong board). Build one from perfboard + 3.5 mm terminal blocks, or use Dupont jumpers. |
| ELE-37 | Arm power adapters (2) | 0 | - | - | - | SKIP | Waiting on SIGRobotics. Voltage not confirmed (5 V 8 A vs 12 V 8 A). Not checked. Once confirmed, order tonight: Thursday delivery needs ordering by ~23:30 EDT, or buy at Micro Center. |
| ELE-38 | Power strip, 6 outlets, individual switches | 1 | [B0GF26Y1TF](https://www.amazon.com/dp/B0GF26Y1TF) | $19.99 | Thu Oct 15 (Prime) | YES | ORDER (or CVS/Target). Individual switches per outlet (no single master). Label ARMS OFF on the arm outlets. Checked from search results only, not the product page. |
| ELE-39 | 4-core shielded cable 22 AWG, 25 ft | 1 | [B0D9JY3MC4](https://www.amazon.com/dp/B0D9JY3MC4) | $16.99 | Thu Oct 15 (Prime) | YES | ORDER only if HX711 goes in EL-02. 22 AWG (no 26 AWG Thursday option). Conditional per BOM. |
| CON-01 | 3M 4950 VHB 1 in x 5 yd | 1 | [B007Y7GIKI](https://www.amazon.com/dp/B007Y7GIKI) | $22.29 | Thu Oct 15 (Prime) | YES | ORDER |
| CON-02 | Cork board 3 mm, 12x12 in, 8-pack | 1 | [B0CKL6KLQS](https://www.amazon.com/dp/B0CKL6KLQS) | $16.99 | Thu Oct 15 (Prime) | YES | ORDER. Cut an 80 mm disc. |
| CON-03 | 1 mm (1/25 in) adhesive silicone sheet 9x12 in | 1 | [B0CZNYD9PP](https://www.amazon.com/dp/B0CZNYD9PP) | $8.99 | Thu Oct 15 (Prime) | YES | ORDER |
| CON-05 | Plastic drop cloth 9x12 ft 4 mil (Trimaco) | 1 | [B00004YOTS](https://www.amazon.com/dp/B00004YOTS) | $11.69 | Thu Oct 15 (Prime) | YES | ORDER (cut to 4x8) |
| CON-06 | Absorbent spill pads (Oil Eater universal) | 1 | [B09X24M4B8](https://www.amazon.com/dp/B09X24M4B8) | $8.40 | Thu Oct 15 (Prime) | YES | ORDER. Check pad count on page; CVS/Home Depot fallback. |
| CON-07 | Kapton tape 4-pack (ELEGOO) | 1 | [B072Z92QZ2](https://www.amazon.com/dp/B072Z92QZ2) | $9.99 | Thu Oct 15 (Prime) | YES | ORDER |
| CON-08 | ASI 388 electronic-grade silicone, 2.8 oz squeeze tube | 1 | [B0063U2RT8](https://www.amazon.com/dp/B0063U2RT8) | $9.95 | Fri Oct 16 (Prime, date only) | FRI-AM | ORDER (Fri) or LOCAL Home Depot/Ace. Page also offered a second offer with Thursday delivery, which is unclear, so marked Fri. Thursday neutral-cure option B0BN4CPHRJ is a 10.1 oz caulk cartridge and needs a caulk gun. Not practical. |
| CON-09 | Loctite 242 blue threadlocker | 1 | [B000I1RSNS](https://www.amazon.com/dp/B000I1RSNS) | $7.02 | Thu Oct 15 (Prime) | YES | ORDER |
| CON-10 | Heat-shrink kit 580 pcs (Ginsco) | 1 | [B01MFA3OFA](https://www.amazon.com/dp/B01MFA3OFA) | $7.99 | Thu Oct 15 (Prime) | YES | ORDER |
| CON-11 | Zip ties 4 in, 200 pcs | 1 | [B0BC1VH4XB](https://www.amazon.com/dp/B0BC1VH4XB) | $3.99 | Thu Oct 15 (Prime) | YES | ORDER |
| CON-12 | Adhesive zip-tie mounts 3/4 in, 100 pcs (XHF) | 1 | [B07M69LK65](https://www.amazon.com/dp/B07M69LK65) | $6.99 | Thu Oct 15 (Prime) | YES | ORDER |
| CON-14 | PTFE adhesive glides, 20 pcs | 1 | [B08HWC3CSP](https://www.amazon.com/dp/B08HWC3CSP) | $8.99 | Thu Oct 15 (Prime) | YES | ORDER |
| CON-15 | Lazy Susan bearing, 8-pack | 1 | [B08CY2P8KZ](https://www.amazon.com/dp/B08CY2P8KZ) | $15.99 | Thu Oct 15 (Prime) | YES | ORDER. Listing says 4 in square; BOM says 3.7 in x 9.4 mm. Confirm it is the same part as in CAD. |
| CON-17 | SUNLU TPU 95A 1.75 mm 1 kg | 1 | [B0BXNWK6NS](https://www.amazon.com/dp/B0BXNWK6NS) | $21.99 | Thu Oct 15 (Prime) | YES | ORDER only if not on hand. TPU parts (GR-03, ST-09) are printed before travel. A Boston delivery only helps if a printer is available there. |
| CON-19 | VELCRO heavy-duty 4x2 in strips, 8 sets | 1 | [B09BNPX3XJ](https://www.amazon.com/dp/B09BNPX3XJ) | $8.65 | Thu Oct 15 (Prime) | YES | ORDER |
| CON-20 | 2020 slot cover strip, 6 m | 1 | [B09KPZBTB9](https://www.amazon.com/dp/B09KPZBTB9) | $11.98 | Thu Oct 15 (Prime) | YES | ORDER. Its purpose was the N20 lead. Still useful for the FB5311M lead. |
| CON-21 | Electrical tape, 4 colours incl. red + blue | 1 | [B0C62DM4H8](https://www.amazon.com/dp/B0C62DM4H8) | $7.89 | Thu Oct 15 (Prime) | YES | ORDER |
| CON-22 | MAIYUM 63/37 rosin-core solder 0.8 mm 50 g | 1 | [B075WB98FJ](https://www.amazon.com/dp/B075WB98FJ) | $8.99 | Thu Oct 15 (Prime) | YES | ORDER. Leaded. No separate flux listed; rosin core is enough for this wiring. |
| CON-23 | 120-grit sandpaper 9x11, 12 sheets | 1 | [B0BWN8J1FZ](https://www.amazon.com/dp/B0BWN8J1FZ) | $8.99 | Thu Oct 15 (Prime) | YES | ORDER |
| TOO-01 | PINECIL soldering iron | 1 | [B096X6SG13](https://www.amazon.com/dp/B096X6SG13) | $39.99 | Thu Oct 15 (Prime) | YES | ORDER (skip if owned). Needs a USB-C PD (>=45 W) or DC barrel supply, which is not included. |
| TOO-02 | AMTOVL long ball-end hex key set 1.5-10 mm, 9 pcs | 1 | [B0CJBRYQF3](https://www.amazon.com/dp/B0CJBRYQF3) | $9.99 | Thu Oct 15 (Prime) | YES | ORDER. TSA <=7 in: the 8/10 mm keys are probably longer; leave them in Boston. |
| TOO-03 | 14 mm HSS drill bit, 1/2 in reduced shank | 1 | [B07S2DCVR2](https://www.amazon.com/dp/B07S2DCVR2) | $8.99 | Thu Oct 15 (Prime) | YES | ORDER early. Thursday cutoff is earlier (~16:45 EDT). Check overall length <=7 in. |
| TOO-04 | GMTOOLS HSS countersink set, 5 pcs | 1 | [B0CWLCZ51W](https://www.amazon.com/dp/B0CWLCZ51W) | $13.99 | Thu Oct 15 (Prime) | YES | ORDER |
| TOO-05 | AstroAI TRMS multimeter | 1 | [B08DHHJPS1](https://www.amazon.com/dp/B08DHHJPS1) | $18.99 | Thu Oct 15 (Prime) | YES | ORDER (skip if owned) |
| TOO-06 | travel inspira luggage scale | 1 | [B07QFTGGYF](https://www.amazon.com/dp/B07QFTGGYF) | $9.99 | Thu Oct 15 (Prime) | YES | ORDER |
| SAF-01 | Quest ANSI Z87.1 safety glasses, 2-pack | 1 | [B0CZ7K4Q9S](https://www.amazon.com/dp/B0CZ7K4Q9S) | $7.99 | Thu Oct 15 (Prime) | YES | ORDER |
| SAF-02 | Indirect-vent lab splash goggles | 2 | [B0CJVDBZW3](https://www.amazon.com/dp/B0CJVDBZW3) | $7.99 x2 = $15.98 | Thu Oct 15 (Prime) | YES | ORDER qty 2. Checked from search results only, not the product page. Pack count not confirmed: if it is a 2-pack, order 1. Backup: EMI #414 B00XWQU2Q6 $9.99 (Thu) or CVS. |
| SAF-03 | Supmedic nitrile gloves, 100 | 1 | [B0C9S5PMSD](https://www.amazon.com/dp/B0C9S5PMSD) | $8.97 | Thu Oct 15 (Prime) | YES | ORDER (pick size) |
| CLB-01 | MAGIKON 100 g M2 calibration weight | 1 | [B078N1TRDC](https://www.amazon.com/dp/B078N1TRDC) | $4.99 | Thu Oct 15 (Prime) | YES | ORDER |

The JSON file has seller, stock and rating per item, plus the Thursday order cutoffs.

## ORDER NOW (Prime, arrives Thu)

Order first, before ~15:00 EDT: **ELE-23**, then **TOO-03** and **GLS-02**, which have early cutoffs.

- GLS-01 Karter 250 mL Erlenmeyer flask: qty 2, $8.20: https://www.amazon.com/dp/B006VYY10Y
- GLS-02 Glass stir rods 6.35 x 150, pack of 4: qty 1, $6.99: https://www.amazon.com/dp/B099QK8PX8
- GLS-03 100 mL borosilicate graduated cylinder (Karter): qty 1, $10.99: https://www.amazon.com/dp/B006UKIASI
- LAB-03 EISCO 4 in PP funnel: qty 1, $9.99: https://www.amazon.com/dp/B017UYYKSQ
- FAS-02 ISO 7380 M4x20 button head, 50 pcs (Fullerkreg): qty 1, $8.89: https://www.amazon.com/dp/B07H17FG9R
- FAS-03 SHCS M4x20 12.9 (arm back row): qty 1, $8.99: https://www.amazon.com/dp/B0CHJDMJ3H
- FAS-04 2020 M4 drop-in T-nut, 100 pcs (HELIFOUNER): qty 1, $5.99: https://www.amazon.com/dp/B0B1LTL6M5
- FAS-05 M3 SHCS kit 720 pcs M3x6-30 (+washers): qty 1, $9.99: https://www.amazon.com/dp/B0FG2BRXL3
- FAS-08 DIN 985 M3 nylon locknut, 120 pcs: qty 1, $9.23: https://www.amazon.com/dp/B0FJ8QP76C
- FAS-09 M3x12 set screw (grub): qty 1, $6.89: https://www.amazon.com/dp/B0DDHL6P99
- FAS-11 M5 SHCS kit 272 pcs M5x8-35: qty 1, $9.99: https://www.amazon.com/dp/B0FGV561HZ
- FAS-13 2020 M5 T-nut + M5 screw kit, 240 pcs: qty 1, $12.99: https://www.amazon.com/dp/B0DMCS8KW4
- FAS-16 ruthex M5 heat-set inserts, 50: qty 1, $9.99: https://www.amazon.com/dp/B07YSVXWS8
- FAS-18 M3 brass standoff kit, 120 pcs: qty 1, $8.99: https://www.amazon.com/dp/B06XQ33Y9X
- HDW-01 F625ZZ flanged bearing, 10 pcs: qty 1, $8.49: https://www.amazon.com/dp/B0G1B256ZS
- HDW-04 BESSEY CM34DR C-clamp, 2-pack: qty 1, $19.06: https://www.amazon.com/dp/B0CBZ9J74Y
- HDW-07 ABS project box 200x120x75 (IP65): qty 1, $9.99: https://www.amazon.com/dp/B06XSQZ5M6
- ELE-02 2S LiPo balance charger, AC input, XT60 (OVONIC Mate1): qty 1, $50.99: https://www.amazon.com/dp/B0G6CV6BNR
- ELE-03 LiPo safe bag (Zeee): qty 1, $13.49: https://www.amazon.com/dp/B07KZQZBN2
- ELE-04 LiPo cell checker/alarm 1-8S: qty 1, $5.99: https://www.amazon.com/dp/B013U1CP08
- ELE-05 Sabrent 4-port powered USB 3.0 hub (HB-UMP3): qty 1, $19.99: https://www.amazon.com/dp/B00TPMEOYM
- ELE-07 USB-A to micro-USB data cable, 2-pack: qty 1, $7.25: https://www.amazon.com/dp/B0719H12WD
- ELE-08 ShangHJ 1 kg load cell + HX711, 2 sets: qty 1, $9.99: https://www.amazon.com/dp/B09K7G51KJ
- ELE-12 20 AWG twisted JR servo ext. w/ clip, 120 cm, 5-pack (BackBayRC): qty 1, $24.49: https://www.amazon.com/dp/B0CXR2YBS4
- ELE-13 20 AWG twisted JR servo ext. w/ clip, 30 cm, 5-pack (BackBayRC): qty 1, $14.49: https://www.amazon.com/dp/B0CXQ8RZH8
- ELE-14 16 AWG silicone wire, 10 ft red + 10 ft black: qty 1, $7.99: https://www.amazon.com/dp/B0D93K21TN
- ELE-15 20 AWG silicone wire, 10 ft red + 10 ft black (BNTECHGO): qty 1, $8.48: https://www.amazon.com/dp/B01AAX64EC
- ELE-16 22 AWG stranded hook-up wire, 6 colours: qty 1, $12.79: https://www.amazon.com/dp/B089CQHRDT
- ELE-17 WAGO 221 12-pc kit (3x 221-415, 3x 413, 3x 412, 3x 2401): qty 1, $12.45: https://www.amazon.com/dp/B0CJ5QF4Z2
- ELE-18 Inline ATO fuse holder 16 AWG, 4-pack (+20 fuses): qty 1, $7.99: https://www.amazon.com/dp/B0F6NPV287
- ELE-19 ATO blade fuse 3 A, 20 pcs: qty 1, $3.99: https://www.amazon.com/dp/B0DHS1GTC7
- ELE-20 ATO blade fuse 1 A, 25 pcs: qty 1, $4.99: https://www.amazon.com/dp/B0DSCF5H9J
- ELE-21 ATO blade fuse 10 A, 25 pcs: qty 1, $4.99: https://www.amazon.com/dp/B0DSCGW488
- ELE-22 XT60 M-F lead with blade-fuse holder, 2 pcs: qty 1, $12.99: https://www.amazon.com/dp/B0BZ7Y1DQY
- ELE-23 Taiss 22 mm e-stop 2NC latching, in station box: qty 1, $16.99: https://www.amazon.com/dp/B07GPF76R1
- ELE-24 HiLetgo 5 V 1-ch relay module, H/L trigger, 2 pcs: qty 1, $7.39: https://www.amazon.com/dp/B00LW15A4W
- ELE-25 Metal film resistor kit 1/4 W 1%, 50 values: qty 1, $8.99: https://www.amazon.com/dp/B0CDWVLTM1
- ELE-26 HiLetgo INA226 module, 2 pcs: qty 1, $10.99: https://www.amazon.com/dp/B0CDWXB8PG
- ELE-28 Rubycon 2200 uF 16 V low-ESR: qty 1, $6.99: https://www.amazon.com/dp/B0FVGBGMW2
- ELE-29 FlashHobby M45CHW 45 kg servo (carousel + stage): qty 3, $44.99: https://www.amazon.com/dp/B09VBFZ9KW (ELE-29 + ELE-30 -> order qty 3 total)
- ELE-31 Treedix 25T Al disc horn, 10 pcs: qty 1, $8.99: https://www.amazon.com/dp/B0875ZS9KF
- ELE-32 470 uF 16 V electrolytic, 8x12 mm: qty 1, $5.99: https://www.amazon.com/dp/B0CMQCQMH5
- ELE-33 Monolithic ceramic cap kit, 24 values (incl. 47 nF, 100 nF): qty 1, $9.99: https://www.amazon.com/dp/B0C1V8Q93P
- ELE-34 A3144 Hall sensor, 20 pcs: qty 1, $6.99: https://www.amazon.com/dp/B0CZ6QXMZ2
- ELE-35 N52 6x2 mm magnets, 50 pcs: qty 1, $9.99: https://www.amazon.com/dp/B0H55FXL9W
- ELE-38 Power strip, 6 outlets, individual switches: qty 1, $19.99: https://www.amazon.com/dp/B0GF26Y1TF
- ELE-39 4-core shielded cable 22 AWG, 25 ft: qty 1, $16.99: https://www.amazon.com/dp/B0D9JY3MC4
- CON-01 3M 4950 VHB 1 in x 5 yd: qty 1, $22.29: https://www.amazon.com/dp/B007Y7GIKI
- CON-02 Cork board 3 mm, 12x12 in, 8-pack: qty 1, $16.99: https://www.amazon.com/dp/B0CKL6KLQS
- CON-03 1 mm (1/25 in) adhesive silicone sheet 9x12 in: qty 1, $8.99: https://www.amazon.com/dp/B0CZNYD9PP
- CON-05 Plastic drop cloth 9x12 ft 4 mil (Trimaco): qty 1, $11.69: https://www.amazon.com/dp/B00004YOTS
- CON-06 Absorbent spill pads (Oil Eater universal): qty 1, $8.40: https://www.amazon.com/dp/B09X24M4B8
- CON-07 Kapton tape 4-pack (ELEGOO): qty 1, $9.99: https://www.amazon.com/dp/B072Z92QZ2
- CON-09 Loctite 242 blue threadlocker: qty 1, $7.02: https://www.amazon.com/dp/B000I1RSNS
- CON-10 Heat-shrink kit 580 pcs (Ginsco): qty 1, $7.99: https://www.amazon.com/dp/B01MFA3OFA
- CON-11 Zip ties 4 in, 200 pcs: qty 1, $3.99: https://www.amazon.com/dp/B0BC1VH4XB
- CON-12 Adhesive zip-tie mounts 3/4 in, 100 pcs (XHF): qty 1, $6.99: https://www.amazon.com/dp/B07M69LK65
- CON-14 PTFE adhesive glides, 20 pcs: qty 1, $8.99: https://www.amazon.com/dp/B08HWC3CSP
- CON-15 Lazy Susan bearing, 8-pack: qty 1, $15.99: https://www.amazon.com/dp/B08CY2P8KZ
- CON-17 SUNLU TPU 95A 1.75 mm 1 kg: qty 1, $21.99: https://www.amazon.com/dp/B0BXNWK6NS
- CON-19 VELCRO heavy-duty 4x2 in strips, 8 sets: qty 1, $8.65: https://www.amazon.com/dp/B09BNPX3XJ
- CON-20 2020 slot cover strip, 6 m: qty 1, $11.98: https://www.amazon.com/dp/B09KPZBTB9
- CON-21 Electrical tape, 4 colours incl. red + blue: qty 1, $7.89: https://www.amazon.com/dp/B0C62DM4H8
- CON-22 MAIYUM 63/37 rosin-core solder 0.8 mm 50 g: qty 1, $8.99: https://www.amazon.com/dp/B075WB98FJ
- CON-23 120-grit sandpaper 9x11, 12 sheets: qty 1, $8.99: https://www.amazon.com/dp/B0BWN8J1FZ
- TOO-01 PINECIL soldering iron: qty 1, $39.99: https://www.amazon.com/dp/B096X6SG13
- TOO-02 AMTOVL long ball-end hex key set 1.5-10 mm, 9 pcs: qty 1, $9.99: https://www.amazon.com/dp/B0CJBRYQF3
- TOO-03 14 mm HSS drill bit, 1/2 in reduced shank: qty 1, $8.99: https://www.amazon.com/dp/B07S2DCVR2
- TOO-04 GMTOOLS HSS countersink set, 5 pcs: qty 1, $13.99: https://www.amazon.com/dp/B0CWLCZ51W
- TOO-05 AstroAI TRMS multimeter: qty 1, $18.99: https://www.amazon.com/dp/B08DHHJPS1
- TOO-06 travel inspira luggage scale: qty 1, $9.99: https://www.amazon.com/dp/B07QFTGGYF
- SAF-01 Quest ANSI Z87.1 safety glasses, 2-pack: qty 1, $7.99: https://www.amazon.com/dp/B0CZ7K4Q9S
- SAF-02 Indirect-vent lab splash goggles: qty 2, $7.99: https://www.amazon.com/dp/B0CJVDBZW3
- SAF-03 Supmedic nitrile gloves, 100: qty 1, $8.97: https://www.amazon.com/dp/B0C9S5PMSD
- CLB-01 MAGIKON 100 g M2 calibration weight: qty 1, $4.99: https://www.amazon.com/dp/B078N1TRDC

### Order now, arrives Fri Oct 16 (no Thursday option found)

- LAB-01 EISCO 50 mL PP beaker (single per listing): qty 6, $9.19: https://www.amazon.com/dp/B00BHLE5AW
- LAB-02 EISCO 100 mL PP beaker, 12-pack: qty 1, $16.29: https://www.amazon.com/dp/B00BHLE5RU
- ELE-27 2512 2 W R010 shunt resistor, 50 pcs: qty 1, $5.99: https://www.amazon.com/dp/B0FVM8PRL5
- CON-08 ASI 388 electronic-grade silicone, 2.8 oz squeeze tube: qty 1, $9.95: https://www.amazon.com/dp/B0063U2RT8

## LOCAL PICKUP in Boston/Cambridge

- **ELE-17 (4th Wago 221-415)**: Micro Center Cambridge, 730 Memorial Dr (call to confirm stock), or the nearest Home Depot / Ace Hardware
- **ELE-36 Mega PRO terminal breakout**: Micro Center Cambridge, 730 Memorial Dr: perfboard + 3.5 mm screw terminal blocks; or skip and use Dupont
- **LAB-04 small PP bin (if kept)**: CVS / Target Fenway (1341 Boylston St)
- **CON-08 neutral-cure silicone (if Fri too late)**: Home Depot or Ace Hardware: neutral-cure silicone in a squeeze tube
- **ELE-37 arm adapters (once voltage confirmed)**: Micro Center Cambridge (5 V / 12 V 8 A 5.5x2.1 bricks) if Amazon cutoff missed
- **Backup for any late Thu item**: Micro Center (wire, fuses, Wago, USB hub, LiPo bag, multimeter); Home Depot/Ace (screws, threadlock, drop cloth, clamps); CVS (gloves, goggles, zip ties, tape)

## PROBLEMS

- PRIME REQUIRED: every Thursday/Friday date is the Prime date. Without Prime all items show FREE delivery Mon Oct 19 (non-Prime) - too late. Order from a Prime account.
- EARLY CUTOFFS (Thursday delivery, from a 13:15 EDT check): ELE-23 e-stop (B07GPF76R1) ~15:05 EDT; TOO-03 14 mm drill ~16:45; GLS-02 stir rods ~16:45. Most others ~19:30-23:50. Place the whole order before 15:00 EDT today.
- No delivery time window was shown (not signed in); Amazon only gave dates. Prime 1-day usually lands by 10 PM, so 'Fri Oct 16' is NOT guaranteed morning.
- FAS-03 BOM link B017NENNVS: no buy box (no seller, price or delivery). Replaced by the M4 12.9 kit B0CHJDMJ3H, which also covers FAS-14.
- FAS-04 BOM link B0DJG8FFGS: Oct 26-Nov 4. BOM alt B09FSJXB15: Wed Oct 21. Both too late. Replaced by B0B1LTL6M5 (Thu).
- FAS-14 BOM link B074TFLBFQ: Oct 26-Nov 3, too late. Covered by B0CHJDMJ3H.
- LAB-01 50 mL EISCO beakers (B00BHLE5AW): Friday only, sold singly ($9.19 each x 6), only 10 left. No Thursday PP 50 mL beaker matching the 43 OD spec found. Critical for the carousel: order now.
- LAB-02 EISCO 100 mL 12-pack: Friday only.
- ELE-36 Mega 2560 PRO screw-terminal shield: no compatible product (Amazon shields are for the full-size Mega R3). Build from perfboard (Micro Center) or skip.
- ELE-17 Wago: the Thursday 12-pc kit has only 3x 221-415 (need 4). Buy 1 locally, or the genuine 25-pk (B0107SYYGU, Fri only, cutoff ~15:50 EDT).
- ELE-37 arm power adapters: SKIPPED, the voltage (5 V vs 12 V, >=6.5 A) is unconfirmed by SIGRobotics. Order by ~23:30 EDT tonight for Thursday, or buy at Micro Center.
- ELE-20 1 A fuse, ELE-25 STBY pull-down, ELE-33 N20 caps, CON-20 N20 lead cover: their documented purpose was the dropped TB6612/N20. Cheap and harmless, but confirm they are still needed.
- Low stock: FAS-09 grub screws (2 left), HDW-01 bearings (5 left), LAB-01 (10 left), ELE-31 horns (11 left), FAS-18 (13 left), ELE-29/30 servos (16 left).
- HDW-07 box is 200x120x75 outside; the CAD envelope is 200x90x60. Re-check the plan3 scene.
- CON-15 lazy Susan listing is '4 inch square'; the BOM says 3.7 in x 9.4 mm. Confirm it is the same part.
- ELE-38 power strip and SAF-02 goggles were checked from search results only (Prime Tomorrow), not from their product pages.
- Many BOM rows say 'On README Oct 13 Amazon list; confirm with the ordering teammate before buying again'. Check for a duplicate order before buying.

## Total cost

- Thursday items: $1,000.12
- Friday items: $87.37
- **Total Amazon: $1,087.49** (before tax, Prime shipping free). Excludes local purchases, arm adapters (ELE-37) and the buy-in-Boston rows.
- If you skip what you may already own (Pinecil $39.99, multimeter $18.99, charger $50.99, TPU $21.99, 2 servos $89.98), the total drops by $221.94 to $865.55.
