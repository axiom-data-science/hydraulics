create role web_anon nologin;
grant web_anon to postgres;

grant usage on schema public to web_anon;
grant select on all tables in schema public to web_anon;