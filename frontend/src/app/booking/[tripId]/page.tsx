"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { BookingConsentCard } from "@/components/journey/BookingConsentCard";
import { JourneyTimeline } from "@/components/journey/JourneyTimeline";
import { PriceBreakdown } from "@/components/journey/PriceBreakdown";
import { EmptyState } from "@/components/shared/Status";
import { WalletBalanceCard } from "@/components/wallet/WalletBalanceCard";
import { WalletTopUpDialog } from "@/components/wallet/WalletTopUpDialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBookingController } from "@/controllers/booking-controller";
import { useWalletController } from "@/controllers/wallet-controller";
import { formatInr } from "@/lib/utils";
import { getSelectedItinerary, useJourneyStore } from "@/store/journey-store";

export default function BookingPage() {
  const params = useParams<{ tripId: string }>();
  const [consent, setConsent] = useState(false);
  const userId = useJourneyStore((state) => state.userId);
  const plan = useJourneyStore((state) => state.activePlan);
  const selectedId = useJourneyStore((state) => state.selectedItineraryId);
  const returnPlan = useJourneyStore((state) => state.returnPlan);
  const selectedReturnId = useJourneyStore((state) => state.selectedReturnItineraryId);
  const booking = useJourneyStore((state) => state.booking);
  const itinerary = getSelectedItinerary(plan, selectedId);
  const returnItinerary = getSelectedItinerary(returnPlan, selectedReturnId);
  const wallet = useWalletController(userId);
  const confirm = useBookingController();

  if (!plan || plan.trip_id !== params.tripId || !itinerary || !selectedId) {
    return <EmptyState title="No selected trip to confirm" message="Go back to Plan and choose an itinerary. This prevents confirming a stale or missing trip." />;
  }

  const confirmedPlan = plan;
  const confirmedSelectedId = selectedId;
  const shortfall = Math.max(0, itinerary.total_price - (wallet.balanceQuery.data?.balance ?? 0));

  function confirmBooking() {
    confirm.mutate({
      trip_id: confirmedPlan.trip_id,
      user_id: userId,
      itinerary_id: confirmedSelectedId,
      user_confirmed: true,
      idempotency_key: `frontend-${confirmedPlan.trip_id}-${confirmedSelectedId}`,
    });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <section className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Review and consent</h1>
          <p className="text-sm text-slate-500">No booking request is sent until you explicitly consent.</p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>{returnItinerary ? "Onward journey" : "Selected itinerary"}</CardTitle>
          </CardHeader>
          <CardContent><JourneyTimeline itinerary={itinerary} booking={booking?.booking} /></CardContent>
        </Card>
        {returnItinerary ? (
          <Card>
            <CardHeader>
              <CardTitle>Return journey</CardTitle>
              <p className="mt-1 text-sm text-slate-500">
                {returnPlan?.origin.name} to {returnPlan?.destination.name}
              </p>
            </CardHeader>
            <CardContent><JourneyTimeline itinerary={returnItinerary} /></CardContent>
          </Card>
        ) : null}
        {booking?.booking ? (
          <Card>
            <CardHeader><CardTitle>Booking result</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>Status: <strong>{booking.booking.status}</strong></p>
              <p>Total charged: {formatInr(booking.booking.total_charged)}</p>
              {booking.booking.error ? <p className="text-red-700">{booking.booking.error}</p> : null}
              <Link href="/active" className="inline-flex h-10 items-center rounded-md bg-brand-600 px-4 text-sm font-medium text-white shadow-brand hover:bg-brand-700">Track active journey</Link>
            </CardContent>
          </Card>
        ) : null}
      </section>
      <aside className="space-y-4">
        <WalletBalanceCard wallet={wallet.balanceQuery.data} />
        <PriceBreakdown itinerary={itinerary} />
        {shortfall > 0 ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <div className="flex gap-2"><AlertCircle className="h-4 w-4" /> Wallet is short by {formatInr(shortfall)}.</div>
            <p className="mt-2">Booking will fail until the wallet covers the fare — top up the shortfall below before confirming.</p>
          </div>
        ) : null}
        <WalletTopUpDialog
          loading={wallet.topUpMutation.isPending}
          onTopUp={(amount) => wallet.topUpMutation.mutate({ amount, trip_id: confirmedPlan.trip_id, description: "Pre-booking top-up" })}
        />
        <BookingConsentCard
          consent={consent}
          onConsent={setConsent}
          onConfirm={confirmBooking}
          loading={confirm.isPending}
          disabled={Boolean(booking?.booking?.all_confirmed)}
        />
      </aside>
    </div>
  );
}
