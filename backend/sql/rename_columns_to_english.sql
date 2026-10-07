-- Ejecutar una sola vez en pgAdmin sobre la base existente, con la API detenida.
-- Conserva datos, tablas, claves foráneas y restricciones.
-- Una base nueva creada con los modelos actualizados no necesita este script.
BEGIN;

ALTER TABLE public.establecimientos RENAME COLUMN nombre TO name;
ALTER TABLE public.establecimientos RENAME COLUMN comuna TO commune;
ALTER TABLE public.establecimientos RENAME COLUMN capacidad_camas TO bed_capacity;

ALTER TABLE public.ingresos_diarios RENAME COLUMN fecha TO date;
ALTER TABLE public.ingresos_diarios RENAME COLUMN establecimiento_id TO establishment_id;
ALTER TABLE public.ingresos_diarios RENAME COLUMN casos_respiratorios TO respiratory_cases;
ALTER TABLE public.ingresos_diarios RENAME COLUMN grupo_etario TO age_group;

COMMIT;
