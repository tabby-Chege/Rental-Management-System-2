DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'properties' AND column_name = 'address'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'properties' AND column_name = 'address_line'
    ) THEN
        ALTER TABLE properties RENAME COLUMN address TO address_line;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'properties' AND column_name = 'state'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'properties' AND column_name = 'region'
    ) THEN
        ALTER TABLE properties RENAME COLUMN state TO region;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'properties' AND column_name = 'zip_code'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'properties' AND column_name = 'postal_code'
    ) THEN
        ALTER TABLE properties RENAME COLUMN zip_code TO postal_code;
    END IF;
END $$;

ALTER TABLE properties
    ADD COLUMN IF NOT EXISTS country VARCHAR(2) NOT NULL DEFAULT 'KE',
    ADD COLUMN IF NOT EXISTS time_zone VARCHAR(64) NOT NULL DEFAULT 'Africa/Nairobi',
    ADD COLUMN IF NOT EXISTS currency VARCHAR(3) NOT NULL DEFAULT 'KES';

ALTER TABLE properties
    ALTER COLUMN region DROP NOT NULL;

UPDATE tenants
SET phone = '+254' || SUBSTRING(phone FROM 2)
WHERE phone ~ '^0[0-9]{9}$';

ALTER TABLE units
    ALTER COLUMN rent_amount TYPE NUMERIC(12, 3)
    USING rent_amount::NUMERIC(12, 3);

ALTER TABLE leases
    ALTER COLUMN monthly_rent TYPE NUMERIC(12, 3)
    USING monthly_rent::NUMERIC(12, 3),
    ALTER COLUMN deposit TYPE NUMERIC(12, 3)
    USING deposit::NUMERIC(12, 3);

ALTER TABLE payments
    ALTER COLUMN amount TYPE NUMERIC(12, 3)
    USING amount::NUMERIC(12, 3);
