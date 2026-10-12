import { useParams } from "react-router-dom";

function PropertyDetails() {
  const { id } = useParams();

  return (
    <div>
      <h1>Property Details</h1>
      <p>Showing details for property ID: {id}</p>
    </div>
  );
}

export default PropertyDetails;