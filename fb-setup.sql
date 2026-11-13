-- ============================================================
-- Facebook 看板 · Supabase 一次性设置
-- 在 Supabase → SQL Editor 贴进去 → Run。可以安全重复跑(不删任何数据)。
-- 只改 Supabase,不会影响你现有的 IG 数据。
-- ============================================================

-- 第 1 段:给 posts 表加「转发数」这一列(Facebook 最看重转发)
alter table posts add column if not exists shares integer default 0;

-- 第 2 段:同行名单(来自 同行研究-2026-11-11.md)
--   Username 填专页网址 facebook.com/ 后面那一段(不要 @,不要整条链接也可以)
--   tracker 必须是大写 FB
--   active = false 的是「还没确认」的,核对过专页再到 Table Editor 打勾
insert into competitors (username, tracker, active, notes) values
  ('katacaremy',          'FB', true,  '直接同行 · KATA 天然皮肤修复(最像 Sarah,华文)'),
  ('theraw.skin',         'FB', true,  '直接同行 · The Raw.(药剂师创办;另有一个 FB 页 TheRaw.Malaysia 待确认)'),
  ('alluskinofficial',    'FB', true,  '直接同行 · Alluskin'),
  ('sensavMY',            'FB', true,  '直接同行 · SensaV'),
  ('drdermismalaysia',    'FB', true,  '直接同行 · DR Dermis'),
  ('themineraw',          'FB', true,  '直接同行 · The Mineraw(另有 The Mineraw Beauty 页待确认)'),
  ('cetaphilmalaysia',    'FB', true,  '行业标杆 · Cetaphil Malaysia'),
  ('physiogelmalaysia',   'FB', true,  '行业标杆 · Physiogel Malaysia'),
  ('kinohimitsu',         'FB', true,  '跨界参考 · Kinohimitsu(客户见证影片获客)'),
  ('monaleafmalaysia',    'FB', true,  '跨界参考 · Monaleaf(长期困扰、试过很多都没用的客群)'),
  ('DermaLabSingapore',   'FB', true,  '新加坡直接同行 · Derma Lab(最像小绿瓶的敏感肌精华)'),
  ('Skinlycious',         'FB', true,  '新加坡直接同行 · Skinlycious'),
  ('BSKIN.SG',            'FB', true,  '新加坡直接同行 · B/SKIN(待确认是不是本地品牌)'),
  ('Ceradan311sg',        'FB', true,  '新加坡行业标杆 · Ceradan'),
  ('CetaphilSG',          'FB', true,  '新加坡行业标杆 · Cetaphil Singapore'),
  ('sigiskin',            'FB', false, '新加坡直接同行 · Sigi Skin(FB 显示店面曾关闭,确认还在营业再打勾)')
on conflict do nothing;

-- 看现在在追踪哪些 FB 专页:
-- select username, active, notes from competitors where tracker = 'FB' order by active desc, username;
-- 停掉某个专页(保留数据,只是不再抓):
-- update competitors set active = false where tracker = 'FB' and lower(username) = lower('要停的专页名');
