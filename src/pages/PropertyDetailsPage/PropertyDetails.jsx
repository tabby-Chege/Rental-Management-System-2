import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  getPublicProperty,
  listPublicPropertyUnits,
} from "../../api/propertiesApi";
import { createApplication, listApplications } from "../../api/applicationsApi";
import { startConversation } from "../../api/conversationsApi";
import { getCurrentUser, getToken } from "../../api/authAPI";
import {
  getMyTenantProfile,
  uploadTenantDocument,
} from "../../api/tenantProfilesApi";
import { formatBedroomCount, formatUnitType } from "../../utils/unitForm";
import { formatMoney } from "../../utils/money";
import {
  deletePhoto,
  photoUrl,
  reportListing,
  setPhotoCover,
  uploadPropertyPhoto,
  uploadUnitPhoto,
} from "../../api/mediaApi";
import "./PropertyDetail.css";

function PropertyDetailsPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const selectedUnitId = location.hash.startsWith("#unit-")
    ? location.hash.slice("#unit-".length)
    : "";
  const [property, setProperty] = useState(null);
  const [units, setUnits] = useState([]);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [applicationError, setApplicationError] = useState("");
  const [applicationMessage, setApplicationMessage] = useState("");
  const [inquiryBody, setInquiryBody] = useState("");
  const [inquiryError, setInquiryError] = useState("");
  const [sendingInquiry, setSendingInquiry] = useState(false);
  const [moveInDate, setMoveInDate] = useState("");
  const [message, setMessage] = useState("");
  const [applyingUnitId, setApplyingUnitId] = useState(null);
  const [applicationUnit, setApplicationUnit] = useState(null);
  const [applicationStep, setApplicationStep] = useState(1);
  const [profile, setProfile] = useState(null);
  const [profileDocuments, setProfileDocuments] = useState([]);
  const [uploadingDocument, setUploadingDocument] = useState(false);
  const [uploadingPhoto, setUploadingPhoto] = useState("");
  const [photoError, setPhotoError] = useState("");
  const [selectedRooms, setSelectedRooms] = useState({});
  const [reportReason, setReportReason] = useState("inaccurate");
  const [reportDetails, setReportDetails] = useState("");
  const [reportMessage, setReportMessage] = useState("");
  const [reportError, setReportError] = useState("");
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let ignore = false;

    async function loadProperty() {
      setIsLoading(true);
      setError("");
      try {
        const [result, unitResult] = await Promise.all([
          getPublicProperty(id),
          listPublicPropertyUnits(id, { unitId: selectedUnitId }),
        ]);
        if (!ignore) {
          setProperty(result);
          setUnits(unitResult.units);
        }
      } catch (requestError) {
        if (!ignore) {
          setProperty(null);
          setUnits([]);
          setError(requestError.message || "Could not load property.");
        }
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }

    loadProperty();
    if (getToken()) {
      getCurrentUser()
        .then(async ({ user: currentUser }) => {
          if (!ignore) setUser(currentUser);
          if (currentUser.role === "tenant") {
            const profileResult = await getMyTenantProfile();
            if (!ignore) {
              setProfile(profileResult.profile);
              setProfileDocuments(profileResult.documents ?? []);
            }
          }
        })
        .catch(() => {
          if (!ignore) setUser(null);
        });
    } else {
      setUser(null);
    }
    return () => {
      ignore = true;
    };
  }, [id, retryCount, selectedUnitId]);

  useEffect(() => {
    if (!isLoading && location.hash.startsWith("#unit-")) {
      document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: "center" });
    }
  }, [isLoading, location.hash, units]);

  useEffect(() => {
    if (user?.role !== "tenant" || units.length === 0) return undefined;
    let ignore = false;
    listApplications()
      .then((applications) => {
        if (ignore) return;
        const activeUnitIds = new Set(
          applications
            .filter((application) =>
              ["pending", "waitlisted", "approved", "offered", "paid"].includes(
                application.status,
              )
            )
            .map((application) => application.unit_id),
        );
        setUnits((current) =>
          current.map((unit) => ({
            ...unit,
            has_pending_application: activeUnitIds.has(unit.id),
          }))
        );
      })
      .catch((requestError) => {
        if (!ignore) setApplicationError(requestError.message);
      });
    return () => {
      ignore = true;
    };
  }, [id, retryCount, user, units.length]);

  async function applyForUnit(unit) {
    setApplicationError("");
    setApplicationMessage("");
    setApplyingUnitId(unit.id);
    try {
      const application = await createApplication({
        unit_id: unit.id,
        move_in_date: moveInDate,
        message,
      });
      setApplicationMessage(
        application.status === "waitlisted"
          ? `You are on the waitlist for unit ${unit.unit_number}.`
          : `Application submitted for unit ${unit.unit_number}.`,
      );
      setUnits((current) => current.map((item) =>
        item.id === unit.id ? { ...item, has_pending_application: true } : item
      ));
      setApplicationUnit(null);
      setApplicationStep(1);
      return application;
    } catch (requestError) {
      setApplicationError(requestError.message || "Could not submit your application.");
    } finally {
      setApplyingUnitId(null);
    }
  }

  async function sendPropertyInquiry(event) {
    event.preventDefault();
    setInquiryError("");
    setSendingInquiry(true);
    try {
      const result = await startConversation(property.id, inquiryBody);
      navigate(`/messages?conversation=${result.conversation.id}`);
    } catch (requestError) {
      setInquiryError(requestError.message || "Could not send your question.");
    } finally {
      setSendingInquiry(false);
    }
  }

  async function handleDocumentUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploadingDocument(true);
    setApplicationError("");
    try {
      const result = await uploadTenantDocument(file);
      setProfileDocuments((current) => [result.document, ...current]);
    } catch (requestError) {
      setApplicationError(requestError.message);
    } finally {
      setUploadingDocument(false);
    }
  }

  async function handlePhotoUpload(event, unit) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) return;
    const key = unit ? `unit-${unit.id}` : "property";
    setUploadingPhoto(key);
    setPhotoError("");
    try {
      for (const file of files) {
        const result = unit
          ? await uploadUnitPhoto(unit.id, file, {
              roomId: selectedRooms[unit.id],
            })
          : await uploadPropertyPhoto(property.id, file);
        if (unit) {
          setUnits((current) =>
            current.map((item) =>
              item.id === unit.id
                ? { ...item, photos: [...(item.photos ?? []), result.photo] }
                : item,
            ),
          );
        } else {
          setProperty((current) => ({
            ...current,
            photos: [...(current.photos ?? []), result.photo],
          }));
        }
      }
    } catch (requestError) {
      setPhotoError(requestError.message || "Could not upload the photo.");
    } finally {
      setUploadingPhoto("");
    }
  }

  async function handlePhotoAction(photo, unit, action) {
    setPhotoError("");
    try {
      if (action === "cover") {
        await setPhotoCover(photo.id);
      } else {
        await deletePhoto(photo.id);
      }
      function updatedPhotos(photos = []) {
        if (action === "cover") {
          return photos.map((itemPhoto) => ({
            ...itemPhoto,
            is_cover: itemPhoto.id === photo.id,
          }));
        }
        const remaining = photos.filter((itemPhoto) => itemPhoto.id !== photo.id);
        if (photo.is_cover && remaining.length > 0) {
          remaining[0] = { ...remaining[0], is_cover: true };
        }
        return remaining;
      }
      if (unit) {
        setUnits((current) =>
          current.map((item) =>
            item.id === unit.id
              ? { ...item, photos: updatedPhotos(item.photos) }
              : item,
          ),
        );
      } else {
        setProperty((current) => ({
          ...current,
          photos: updatedPhotos(current.photos),
        }));
      }
    } catch (requestError) {
      setPhotoError(requestError.message || "Could not update the photo.");
    }
  }

  async function handleReportSubmit(event) {
    event.preventDefault();
    setReportError("");
    setReportMessage("");
    try {
      await reportListing({
        property_id: property.id,
        reason: reportReason,
        details: reportDetails,
      });
      setReportMessage("Thank you. Your report has been submitted for review.");
      setReportDetails("");
    } catch (requestError) {
      setReportError(requestError.message || "Could not submit your report.");
    }
  }

  const canManagePhotos =
    user?.role === "admin" ||
    (user?.role === "landlord" && user.id === property.owner_id);

  if (isLoading) {
    return (
      <div className="details-page" aria-live="polite">
        <p>Loading property...</p>
      </div>
    );
  }

  if (error || !property) {
    return (
      <div className="details-page">
        <Link to="/properties" className="details-back">
          Back to properties
        </Link>
        <p className="details-error" role="alert">
          {error || "Property not found."}
        </p>
        {error && (
          <button type="button" onClick={() => setRetryCount((count) => count + 1)}>
            Try again
          </button>
        )}
      </div>
    );
  }

  const unitsByFloor = units.reduce((groups, unit) => {
    (groups[unit.floor_number] ??= []).push(unit);
    return groups;
  }, {});

  return (
    <div className="details-page">
      <Link to="/properties" className="details-back">
        Back to properties
      </Link>
      <header className="details-header">
        <h1>{property.name}</h1>
        <p className="details-address">
          {property.address_line || property.address}, {property.city}
          {property.region || property.state ? `, ${property.region || property.state}` : ""}
          {property.postal_code || property.zip_code ? ` ${property.postal_code || property.zip_code}` : ""}
          {property.country ? `, ${property.country}` : ""}
        </p>
      </header>
      {property.occupancy_summary && (
        <section className="details-occupancy-summary" aria-label="Property occupancy summary">
          <strong>
            {property.occupancy_summary.total_units} units ·{" "}
            {property.occupancy_summary.occupied_units} occupied ·{" "}
            {property.occupancy_summary.reserved_units} reserved ·{" "}
            {property.occupancy_summary.vacant_units} vacant
          </strong>
        </section>
      )}
      {user?.role === "tenant" && property.owner_id !== user.id && (
        <details className="details-box listing-report property-inquiry">
          <summary>Ask the landlord a question</summary>
          <form onSubmit={sendPropertyInquiry}>
            <label>
              Your question
              <textarea
                value={inquiryBody}
                maxLength={5000}
                required
                onChange={(event) => setInquiryBody(event.target.value)}
              />
            </label>
            {inquiryError && <p className="details-error" role="alert">{inquiryError}</p>}
            <button type="submit" disabled={sendingInquiry || !inquiryBody.trim()}>
              {sendingInquiry ? "Sending…" : "Send question"}
            </button>
          </form>
        </details>
      )}
      {!user && (
        <p className="details-inquiry-login">
          <Link to="/login">Log in as a tenant to ask the landlord a question</Link>
        </p>
      )}
      {(property.photos?.length > 0 || canManagePhotos) && (
        <section className="details-box listing-photos" aria-label="Property photos">
          <h2>Property photos</h2>
          {property.photos?.length > 0 && (
            <div className="listing-photo-gallery">
              {property.photos.map((photo) => (
                <figure key={photo.id} className="listing-photo">
                  <img src={photoUrl(photo)} alt={`${property.name} property`} />
                  {photo.is_cover && <figcaption>Cover photo</figcaption>}
                  {canManagePhotos && (
                    <div className="photo-actions">
                      {!photo.is_cover && (
                        <button type="button" onClick={() => handlePhotoAction(photo, null, "cover")}>
                          Set as cover
                        </button>
                      )}
                      <button type="button" onClick={() => handlePhotoAction(photo, null, "delete")}>
                        Delete
                      </button>
                    </div>
                  )}
                </figure>
              ))}
            </div>
          )}
          {canManagePhotos && (
            <label className="photo-upload-control">
              Add property photos
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                disabled={uploadingPhoto === "property"}
                onChange={(event) => handlePhotoUpload(event, null)}
              />
            </label>
          )}
        </section>
      )}
      {photoError && <p className="details-error" role="alert">{photoError}</p>}
      {user && user.id !== property.owner_id && (
        <details className="details-box listing-report">
          <summary>Report this listing</summary>
          <form onSubmit={handleReportSubmit}>
            <label>
              Reason
              <select
                value={reportReason}
                onChange={(event) => setReportReason(event.target.value)}
              >
                <option value="inaccurate">Inaccurate information</option>
                <option value="scam">Potential scam</option>
                <option value="unavailable">No longer available</option>
                <option value="inappropriate">Inappropriate content</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label>
              Details (optional)
              <textarea
                value={reportDetails}
                maxLength={1000}
                onChange={(event) => setReportDetails(event.target.value)}
              />
            </label>
            <button type="submit">Submit report</button>
          </form>
          {reportError && <p role="alert" className="details-error">{reportError}</p>}
          {reportMessage && <p role="status">{reportMessage}</p>}
        </details>
      )}
      {property.description && (
        <section className="details-box">
          <h2>Notes</h2>
          <p>{property.description}</p>
        </section>
      )}
      <section className="details-box details-units">
        <h2>{property.rental_type === "whole_property" ? "Whole property" : "Units at this property"}</h2>
        {units.length === 0 && <p>No units are listed for this property yet.</p>}
        {Object.entries(unitsByFloor)
          .sort(([floorA], [floorB]) => Number(floorA) - Number(floorB))
          .map(([floor, floorUnits]) => (
          <section key={floor}>
          {property.rental_type !== "whole_property" && <h3>Floor {floor}</h3>}
          <ul>
          {floorUnits.map((unit) => (
            <li key={unit.id} id={`unit-${unit.id}`} className="details-unit">
              <div>
                <strong>{unit.unit_number === "Entire property" ? "Entire property" : `Unit ${unit.unit_number}`}</strong>
                <p>
                  {formatUnitType(unit.unit_type, unit.bedrooms)}
                  {unit.layout ? ` · Layout ${unit.layout}` : ""}
                  {" · "}
                  {formatBedroomCount(unit.bedrooms)}
                  {unit.bathrooms != null ? ` · ${unit.bathrooms} bathrooms` : ""}
                  {unit.size != null ? ` · ${unit.size} ${unit.size_unit}` : ""}
                  {unit.furnished ? " · Furnished" : ""}
                  {unit.rent_amount != null
                    ? ` · ${formatMoney(unit.rent_amount, unit.currency)} per month`
                    : ""}
                </p>
                <span className={`manage-badge is-${unit.availability_status || (unit.is_occupied ? "occupied" : "vacant")}`}>
                  {unit.availability_status === "occupied"
                    ? "Occupied"
                    : unit.availability_status === "reserved"
                      ? "Reserved"
                      : "Available"}
                </span>
                {unit.description && <p>{unit.description}</p>}
                {(unit.photos?.length > 0 || canManagePhotos) && (
                  <div className="unit-listing-photos">
                    {unit.photos?.length > 0 && (
                      <div className="listing-photo-gallery">
                        {unit.photos.map((photo) => {
                          const room = unit.rooms?.find((item) => item.id === photo.room_id);
                          return (
                            <figure key={photo.id} className="listing-photo">
                              <img
                                src={photoUrl(photo)}
                                alt={`${unit.unit_number}${room ? ` ${room.name}` : ""}`}
                              />
                              {room && <figcaption>{room.name}</figcaption>}
                              {photo.is_cover && <figcaption>Cover photo</figcaption>}
                              {canManagePhotos && (
                                <div className="photo-actions">
                                  {!photo.is_cover && (
                                    <button type="button" onClick={() => handlePhotoAction(photo, unit, "cover")}>
                                      Set as cover
                                    </button>
                                  )}
                                  <button type="button" onClick={() => handlePhotoAction(photo, unit, "delete")}>
                                    Delete
                                  </button>
                                </div>
                              )}
                            </figure>
                          );
                        })}
                      </div>
                    )}
                    {canManagePhotos && (
                      <label className="photo-upload-control">
                        Add unit photos
                        {unit.rooms?.length > 0 && (
                          <select
                            aria-label={`Tag photo for unit ${unit.unit_number}`}
                            value={selectedRooms[unit.id] ?? ""}
                            onChange={(event) =>
                              setSelectedRooms((current) => ({
                                ...current,
                                [unit.id]: event.target.value,
                              }))
                            }
                          >
                            <option value="">No room tag</option>
                            {unit.rooms.map((room) => (
                              <option key={room.id} value={room.id}>{room.name}</option>
                            ))}
                          </select>
                        )}
                        <input
                          type="file"
                          accept="image/jpeg,image/png,image/webp"
                          multiple
                          disabled={uploadingPhoto === `unit-${unit.id}`}
                          onChange={(event) => handlePhotoUpload(event, unit)}
                        />
                      </label>
                    )}
                  </div>
                )}
                {unit.rooms?.length > 0 && (
                  <ul aria-label={`Rooms in ${unit.unit_number}`}>
                    {unit.rooms.map((room) => (
                      <li key={room.id}>
                        {room.name} · {room.room_type.replaceAll("_", " ")}
                        {room.size != null ? ` · ${room.size} ${room.size_unit}` : ""}
                        {room.description ? ` — ${room.description}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {user?.role === "tenant" && ["vacant", "reserved"].includes(unit.availability_status) && !unit.has_pending_application && (
                <button
                  type="button"
                  className="manage-button"
                  disabled={applyingUnitId === unit.id}
                  onClick={() => {
                    setApplicationError("");
                    setApplicationUnit(unit);
                    setApplicationStep(1);
                  }}
                >
                  {unit.availability_status === "reserved" ? "Join waitlist" : "Apply"}
                </button>
              )}
              {unit.has_pending_application && <span>Application submitted</span>}
            </li>
          ))}
        </ul>
        </section>
        ))}
        {applicationUnit && user?.role === "tenant" && (
          <section className="application-form application-wizard" aria-label="Rental application">
            <h3>Apply for unit {applicationUnit.unit_number}</h3>
            <p className="application-steps">Step {applicationStep} of 4</p>
            {applicationStep === 1 && (
              <div>
                <h4>1. Your profile</h4>
                {profile ? (
                  <>
                    <p>{profile.full_name} · {profile.phone}</p>
                    <p>{profile.employment_status}</p>
                  </>
                ) : (
                  <p>Complete your tenant profile before applying.</p>
                )}
                <Link to="/tenant/details">Review or complete my profile</Link>
              </div>
            )}
            {applicationStep === 2 && (
              <div>
                <h4>2. Supporting documents</h4>
                <p>Upload identity or supporting documents. Documents are private and optional.</p>
                <label>
                  Add a document
                  <input
                    type="file"
                    accept="application/pdf,image/jpeg,image/png,image/webp"
                    disabled={!profile || uploadingDocument}
                    onChange={handleDocumentUpload}
                  />
                </label>
                {uploadingDocument && <p role="status">Uploading…</p>}
                <ul>
                  {profileDocuments.map((item) => (
                    <li key={item.id}>
                      {item.kind} · {Math.ceil(item.file_size / 1024)} KB
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {applicationStep === 3 && (
              <div>
                <h4>3. Move-in date</h4>
                <label>
                  Requested move-in date
                  <input
                    type="date"
                    value={moveInDate}
                    onChange={(event) => setMoveInDate(event.target.value)}
                    required
                  />
                </label>
                <label>
                  Message to the property manager (optional)
                  <textarea
                    value={message}
                    maxLength={5000}
                    onChange={(event) => setMessage(event.target.value)}
                  />
                </label>
              </div>
            )}
            {applicationStep === 4 && (
              <div>
                <h4>4. Review and submit</h4>
                <p>{profile?.full_name} · {profile?.phone}</p>
                <p>{profile?.employment_status}</p>
                <p>{profileDocuments.length} document(s) included</p>
                <p>Requested move-in: {moveInDate}</p>
                {message && <p>{message}</p>}
                <p>Your submitted application keeps a snapshot of these details.</p>
              </div>
            )}
            {applicationError && <p className="details-error" role="alert">{applicationError}</p>}
            <div className="manage-actions">
              <button
                type="button"
                className="manage-button"
                onClick={() => {
                  if (applicationStep === 1) setApplicationUnit(null);
                  else setApplicationStep((step) => step - 1);
                }}
              >
                {applicationStep === 1 ? "Cancel" : "Back"}
              </button>
              {applicationStep < 4 ? (
                <button
                  type="button"
                  className="manage-button"
                  disabled={
                    (applicationStep === 1 && !profile) ||
                    (applicationStep === 3 && !moveInDate)
                  }
                  onClick={() => setApplicationStep((step) => step + 1)}
                >
                  Next
                </button>
              ) : (
                <button
                  type="button"
                  className="manage-button"
                  disabled={applyingUnitId === applicationUnit.id}
                  onClick={() => applyForUnit(applicationUnit)}
                >
                  {applyingUnitId === applicationUnit.id ? "Submitting…" : "Submit application"}
                </button>
              )}
            </div>
          </section>
        )}
        {user?.role === "tenant" && applicationError && (
          <p className="details-error" role="alert">{applicationError}</p>
        )}
        {applicationMessage && <p role="status">{applicationMessage}</p>}
        {!user && <p><Link to="/login">Log in as a tenant to apply</Link></p>}
        {user && user.role !== "tenant" && (
          <p>Applications are available to tenant accounts.</p>
        )}
      </section>
      {(user?.role === "landlord" || user?.role === "admin") &&
        (user?.role === "admin" || user.id === property.owner_id)
        && property.rental_type !== "whole_property" && (
        <Link to={`/units?property_id=${property.id}`}>Manage this property&apos;s units</Link>
      )}
    </div>
  );
}

export default PropertyDetailsPage;
