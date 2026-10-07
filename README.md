# Rental Property Finder

A React prototype that helps prospective renters and property researchers browse property records in selected US cities. Users can search a city's results, narrow them by property age and size, sort the matches, and open a property detail page.

This is a property discovery prototype, not a complete rental-management system. It does not manage leases, tenants, payments, or confirmed rental availability.

## Features

- Browse property records for Austin, Houston, Denver, Atlanta, Chicago, or Seattle.
- Search the returned results by name/address, city, state, or ZIP code.
- Filter by build year and square footage; sort by build year or size.
- View property details and other records in the same city.
- Show loading, empty, API error, and retry states.
- Run with RentCast data or bundled sample data for development and demos.

## Tech Stack

- React 19 and Vite
- React Router
- RentCast Property Records API
- CSS and JavaScript

## Requirements

- Node.js 20.19+ (required by the installed Vite release)
- npm
- A RentCast API key for live API requests; no key is needed in mock mode

## Run Locally

1. Install dependencies:

   ```sh
   npm install
   ```

2. Create a local environment file from the template:

   ```sh
   cp .env.example .env.local
   ```

3. Choose a data mode in `.env.local`:

   ```env
   VITE_USE_MOCK=true
   VITE_RENTCAST_API_KEY=
   ```

   Keep `VITE_USE_MOCK=true` to use bundled sample properties. For live requests, set it to `false` and add your RentCast API key to `VITE_RENTCAST_API_KEY`.

4. Start the development server:

   ```sh
   npm run dev
   ```

5. Open the local URL printed by Vite.

## API Integration

The app uses the [RentCast Property Records API](https://developers.rentcast.io/reference/property-records):

- `GET https://api.rentcast.io/v1/properties?city={city}&state={state}&limit=20` loads a city's records.
- `GET https://api.rentcast.io/v1/properties/{id}` loads an individual record for its detail page.
- Live requests send the API key in the `X-Api-Key` request header.

API requests are isolated in `src/api/rentcastAPI.js`. `src/utils/propertyAdapter.js` maps API and sample records to the fields used by the UI. The city selector changes the API request; text search, filters, and sorting apply to the returned records in the browser.

## Validation

```sh
npm test
npm run lint
npm run build
```

## Project Structure

```text
src/
├── api/             # RentCast requests and mock mode
├── Components/      # Reusable search controls
├── data/            # Supported cities and sample records
├── pages/           # Search and property detail views
└── utils/           # Property normalization and search logic
```

## Known Limitations

- The live search requests at most 20 records for the selected city. Search terms, filters, and sorting only inspect that returned result set; they do not run a full-text search across all RentCast records.
- RentCast property records are not a guarantee that a property is currently available to rent. The prototype does not show verified rent prices or availability.
- Bundled mock records are currently available for Austin, TX only; other locations show an empty result state in mock mode.
- API availability, response limits, and rate limits depend on the RentCast account and plan.
- Vite exposes variables prefixed with `VITE_` in browser-delivered code. Treat the API key used here as visible to users; this client-only setup is suitable for a prototype, not production. A deployed production app should make authenticated API requests through a server-side proxy and protect the key there.
- No hosted deployment is configured yet.

## Team Contributions

- **Tabby:** React Router setup, navigation, base project structure, and API integration coordination
- **Sonia:** RentCast API integration and data-fetching helpers
- **David:** Property cards component and property listing display
- **Luice:** Search filtering, input controls, and property details page
- **Zack:** UI/CSS integration and project documentation
  A React application built with Vite and React Router that enables property managers and tenants to browse rental listings, search properties, and view detailed property information using the RentCast API.
