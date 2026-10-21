ALTER TABLE properties
    ADD COLUMN IF NOT EXISTS rental_type VARCHAR(20) NOT NULL DEFAULT 'multi_unit',
    ADD COLUMN IF NOT EXISTS subtype VARCHAR(30) NOT NULL DEFAULT 'apartment_block',
    ADD COLUMN IF NOT EXISTS floors INTEGER NOT NULL DEFAULT 1;

ALTER TABLE units
    ADD COLUMN IF NOT EXISTS floor_number INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS layout VARCHAR(20),
    ADD COLUMN IF NOT EXISTS size NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS size_unit VARCHAR(20),
    ADD COLUMN IF NOT EXISTS furnished BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS rooms (
    id SERIAL PRIMARY KEY,
    unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    name VARCHAR(80) NOT NULL,
    room_type VARCHAR(30) NOT NULL,
    size NUMERIC(12, 2),
    size_unit VARCHAR(20),
    description VARCHAR(1000),
    CONSTRAINT ck_rooms_size_positive CHECK (size IS NULL OR size > 0),
    CONSTRAINT ck_rooms_type CHECK (
        room_type IN ('bedroom', 'living_room', 'kitchen', 'bathroom', 'balcony', 'other')
    )
);

CREATE INDEX IF NOT EXISTS ix_rooms_unit_id ON rooms(unit_id);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_properties_rental_type') THEN
        ALTER TABLE properties ADD CONSTRAINT ck_properties_rental_type
            CHECK (rental_type IN ('multi_unit', 'whole_property'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_properties_subtype') THEN
        ALTER TABLE properties ADD CONSTRAINT ck_properties_subtype
            CHECK (subtype IN ('apartment_block', 'bungalow', 'maisonette', 'villa', 'townhouse', 'commercial'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_properties_floors') THEN
        ALTER TABLE properties ADD CONSTRAINT ck_properties_floors CHECK (floors >= 1);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_units_floor_number') THEN
        ALTER TABLE units ADD CONSTRAINT ck_units_floor_number CHECK (floor_number >= 1);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_units_size_positive') THEN
        ALTER TABLE units ADD CONSTRAINT ck_units_size_positive CHECK (size IS NULL OR size > 0);
    END IF;
END $$;
