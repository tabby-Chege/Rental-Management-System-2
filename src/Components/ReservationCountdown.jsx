import { useEffect, useState } from "react";
import { formatReservationCountdown } from "../utils/reservationCountdown";

function ReservationCountdown({ deadline }) {
  const [now, setNow] = useState(Date.now);

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  return (
    <p className="manage-status" role="timer" aria-live="off">
      {formatReservationCountdown(deadline, now)}
    </p>
  );
}

export default ReservationCountdown;
