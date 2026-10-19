-- RUN ONCE in Supabase SQL Editor after the three existing tables and RLS policies are created.
-- Your initial SQL should already define public.businesses, public.orders, public.simulations.

-- A private admin allowlist. No client can read or edit it directly.
create table if not exists public.resilience_admins (
 user_id uuid primary key references auth.users(id) on delete cascade
);
alter table public.resilience_admins enable row level security;
revoke all on public.resilience_admins from public, anon, authenticated;

-- Transactions protect saved orders from partial delete-and-insert failures.
create or replace function public.replace_my_orders(p_business_id uuid, p_orders jsonb)
returns void language plpgsql security invoker set search_path = '' as $$
declare v_item jsonb;
begin
  if auth.uid() is null or not exists (
    select 1 from public.businesses where id = p_business_id and user_id = auth.uid()
  ) then raise exception 'You do not own this business'; end if;
  if jsonb_typeof(p_orders) <> 'array' or jsonb_array_length(p_orders) > 12 then
    raise exception 'Orders must be an array with at most 12 items';
  end if;
  delete from public.orders where business_id = p_business_id;
  for v_item in select value from jsonb_array_elements(p_orders) loop
    insert into public.orders(business_id,name,duration,deadline,missed_penalty)
    values (p_business_id,v_item->>'name',(v_item->>'duration')::integer,
       (v_item->>'deadline')::integer,(v_item->>'missed_penalty')::integer);
  end loop;
end $$;
revoke all on function public.replace_my_orders(uuid,jsonb) from public, anon;
grant execute on function public.replace_my_orders(uuid,jsonb) to authenticated;

-- Admin verification is done inside Postgres using the signed-in user's JWT.
create or replace function public.is_resilience_admin()
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.resilience_admins where user_id = (select auth.uid()));
$$;
revoke all on function public.is_resilience_admin() from public, anon;
grant execute on function public.is_resilience_admin() to authenticated;

-- Administrative user list and aggregate counts. Must NEVER be callable by other users.
create or replace function public.resilience_admin_overview()
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare r jsonb;
begin
  if auth.uid() is null or not exists(select 1 from public.resilience_admins where user_id=auth.uid()) then
    raise exception 'Access denied';
  end if;
  select jsonb_build_object(
    'user_count',(select count(*) from auth.users),
    'business_count',(select count(*) from public.businesses),
    'order_count',(select count(*) from public.orders),
    'simulation_count',(select count(*) from public.simulations),
    'users',coalesce((select jsonb_agg(row_to_json(t) order by t.created_at desc)
      from (
        select u.email,u.raw_user_meta_data->>'full_name' as name,
               u.created_at,u.last_sign_in_at,
               (select count(*) from public.businesses b where b.user_id=u.id) as business_count
        from auth.users u
        order by u.created_at desc limit 100
      ) t),'[]'::jsonb)
  ) into r;
  return r;
end $$;
revoke all on function public.resilience_admin_overview() from public,anon;
grant execute on function public.resilience_admin_overview() to authenticated;

-- ADMIN BOOTSTRAP (perform manually in SQL Editor, NEVER in a browser):
-- 1. Sign up for ResilienceOS, verify email, sign in.
-- 2. Supabase > Authentication > Users > copy YOUR user's UUID.
-- 3. Run the following after replacing UUID with YOUR OWN account ID:
-- insert into public.resilience_admins(user_id) values ('YOUR-AUTH-USER-UUID');
-- 4. Sign out and back in to see the Admin panel.
