# 🎭 NightVibe India — Multi-Persona Product & Architecture Review
### Elite Panel: B2C Guest · B2B Venue GM · B2B PR Promoter

**Review Date:** 2026-08-30  
**Codebase:** `kbsingh1399/nightvibe` — Full-stack prototype (React + Tailwind + FastAPI + SQLAlchemy)  
**Reviewers:** Guest Experience Lead · Venue Operations Director · Promoter Growth Strategist

---

## Table of Contents
1. [Persona Friction Matrix](#1-persona-friction-matrix)
2. [Identity, OTP Sign-In & Role Disambiguation](#2-identity-otp-sign-in--role-disambiguation)
3. [Guest Experience Deep-Dive](#3-guest-experience-deep-dive)
4. [Club Owner & Bouncer Experience](#4-club-owner--bouncer-experience)
5. [PR Promoter Experience](#5-pr-promoter-experience)
6. [Direct Mobile OTP Architecture Spec](#6-direct-mobile-otp-architecture-spec)
7. [Production Migration Roadmap](#7-production-migration-roadmap)
8. [Git Delivery Guidelines](#8-git-delivery-guidelines)

---

## 1. Persona Friction Matrix

### 🔴 = Critical · 🟡 = High · 🟢 = Moderate

| # | Persona | Friction Point | Location | Severity | Description |
|---|---------|---------------|----------|----------|-------------|
| **G1** | Guest | No phone OTP login | `AppContext.jsx` | 🔴 | Hardcoded `currentUser` with static phone. Guest must "know" they're a guest. No real auth. |
| **G2** | Guest | PR jargon leaks into UI | `EventDetailModal.jsx` | 🟡 | "Authorized Promoter Bids" and "PR Commission" language confuses casual partygoers. Should be "Your VIP Deals" or "Exclusive Offers". |
| **G3** | Guest | Stag warning has no price impact | `EventDetailModal.jsx` | 🟡 | Warning says "1:1 ratio enforced" but doesn't show surcharge amount. Guest discovers penalty at the door. |
| **G4** | Guest | Payment step loses bid context | `EventDetailModal.jsx` | 🟡 | Switching from 'select' to 'payment' step replaces modal content. Guest forgets which PR deal they picked. |
| **G5** | Guest | QR pass shows internal PR details | `MyPassesModal.jsx` | 🟢 | Pass shows `pr.handle` and `pr.name` — guest doesn't need to see promoter internals on their ticket. |
| **G6** | Guest | No "My Bookings" history | `App.jsx` | 🟡 | Only way to see past bookings is through the passes modal. No dedicated booking history or receipt download. |
| **G7** | Guest | Touch targets too small | `EventDetailModal.jsx` | 🟡 | Male/Female stepper buttons are `w-7 h-7` (28px). WCAG minimum is 44px. |
| **G8** | Guest | No offline pass access | `MyPassesModal.jsx` | 🟡 | If the guest loses connectivity after booking, they can't show their QR pass. No Service Worker caching. |
| **V1** | Venue | No real authentication | `OwnerView.jsx` | 🔴 | Club owner is selected via a dropdown (`Switch Club`). Any browser user can access the gate scanner. |
| **V2** | Venue | Gate scanner is client-side only | `OwnerView.jsx` | 🔴 | `handleInspectTicket` reads from in-memory `bookings` state. No server validation. Trivially spoofable. |
| **V3** | Venue | TOTP verification is simulated | `main.py` L120-130 | 🔴 | `verify-qr-totp` endpoint checks `abs(req.totpNonce - current_nonce) > 1` but never verifies the HMAC signature. The `signature` field is optional and unused. |
| **V4** | Venue | No offline gate capability | `OwnerView.jsx` | 🔴 | Basement clubs with no signal will have a non-functional scanner. No Service Worker or IndexedDB manifest cache. |
| **V5** | Venue | GST/TDS not broken out in ledger | `OwnerView.jsx` ledger tab | 🟡 | Ledger shows `grossAmount`, `venueShare`, `prCommission`, `tdsDeducted` but no GST line item. Non-compliant for GST filing. |
| **V6** | Venue | Escrow settlement is instant (no real hold) | `main.py` L100-140 | 🔴 | `settle-admission` immediately marks escrow as `SETTLED` and credits PR wallet. No Razorpay Route integration. No actual money movement. |
| **V7** | Venue | No rejection photo evidence | `OwnerView.jsx` reject modal | 🟡 | Rejection reasons are text-only. No mandatory photo capture for dress code violations. Disputes will be he-said-she-said. |
| **V8** | Venue | Occupancy counter is not real-time | `OwnerView.jsx` | 🟡 | `currentOccupancy` is a static field updated only on `ADMIT`. No WebSocket push to owner dashboard. |
| **P1** | PR | No dedicated PR onboarding flow | `PromoterView.jsx` | 🔴 | PR is selected via dropdown. No portfolio submission, Instagram verification, or venue authorization request flow. |
| **P2** | PR | Wallet withdrawal is simulated | `PromoterView.jsx` | 🔴 | `handleWithdrawWallet` fires confetti and shows a toast. No actual Razorpay Payout API call. No UPI transfer. |
| **P3** | PR | No bid cooldown or revision limits | `AppContext.jsx` `submitPRBid` | 🟡 | PRs can update bids unlimited times with no cooldown. Enables spam bidding and price manipulation. |
| **P4** | PR | No competitor bid visibility | `PromoterView.jsx` | 🟡 | PR can't see how their bid ranks against competitors. Reduces competitive tension and strategic bidding. |
| **P5** | PR | Commission formula is opaque | `PromoterView.jsx` | 🟡 | `estimatedGrossCommission = max(150, discountGiven + 120)` — the `+120` magic number is unexplained. PRs need transparent commission breakdowns. |
| **P6** | PR | Tier system is display-only | `models.py` | 🟡 | `tier = Column(String, default="Rising Star")` — no computed tier progression based on actual performance metrics. |
| **P7** | PR | Sub-promoter links are client-side only | `PromoterView.jsx` | 🟢 | Generated links (`https://nightvibe.in/e/...`) are constructed client-side with no server-side tracking or attribution. |
| **P8** | PR | No push notifications for bid updates | `PromoterView.jsx` | 🟢 | PR has no way to know when they've been outbid or when a guest books through their link. |

### Security Risk Matrix

| # | Risk | File | Severity | Description |
|---|------|------|----------|-------------|
| **S1** | Hardcoded master secret | `security.py` L5 | 🔴 | `SECRET_MASTER_KEY = "nightvibe_super_secret_master_key_2026"` is committed to source control. Must be in environment variables / vault. |
| **S2** | CORS allow all origins | `main.py` L15 | 🔴 | `allow_origins=["*"]` with `allow_credentials=True` is a security anti-pattern. Allows CSRF from any origin. |
| **S3** | No JWT / session management | `main.py` | 🔴 | No authentication middleware. All endpoints are publicly accessible. No role-based access control. |
| **S4** | In-memory database | `main.py` L25 | 🔴 | `DB_STATE` dict is the entire data store. All data lost on restart. Not suitable for any real usage. |
| **S5** | No Razorpay webhook verification | `main.py` L145 | 🔴 | `razorpay_webhook` accepts raw `dict` with no signature verification. Any attacker can fake payment confirmations. |
| **S6** | TOTP signature not verified at gate | `main.py` L120 | 🔴 | The `verify-qr-totp` endpoint accepts `signature` as optional and never calls `verify_totp_token()`. The HMAC security is completely bypassed. |
| **S7** | No rate limiting | `main.py` | 🟡 | No rate limiting on any endpoint. Brute-force ticket ID enumeration is trivial. |
| **S8** | Ticket ID is low-entropy | `main.py` L85 | 🟡 | `TKT-{uuid4.hex[:4].upper()}` = 16 bits of entropy (65,536 possibilities). Enumerate in minutes. |

---

## 2. Identity, OTP Sign-In & Role Disambiguation

### 2.1 The Core Problem

The current prototype has **three separate role selectors** that create cognitive chaos:

1. **Header dropdown** in `App.jsx` — switches between `guest`, `owner`, `pr`
2. **Owner venue switcher** in `OwnerView.jsx` — `select` dropdown to pick a venue
3. **PR persona switcher** in `PromoterView.jsx` — `select` dropdown to pick a promoter

This means a user can be "Arjun Kapoor the Guest" in one click, then "Trilogy Club Owner" in the next click, then "Rahul the PR" in the third click. There's no identity, no authentication, no role gating.

### 2.2 The Correct Architecture: Phone-First, Role-Second

In India, **mobile phone number IS identity**. Every user — guest, club owner, PR — has a phone. The architecture should be:

```
┌─────────────────────────────────────────────────────────────────┐
│                    IDENTITY FLOW                                 │
│                                                                  │
│  1. User opens app → sees Login screen (not role selector)       │
│  2. Enters +91 mobile number → receives OTP via MSG91/Firebase   │
│  3. Verifies OTP → JWT issued with { sub, phone, roles: [] }    │
│  4. If roles is empty → defaults to GUEST experience             │
│  5. Guest can upgrade to PR or Club Owner via onboarding flows   │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ +91 OTP  │───►│ JWT      │───►│ GUEST    │───►│ Upgrade? │  │
│  │ Login    │    │ Session  │    │ (default)│    │ PR/Owner │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Role Upgrade Paths (Not Role Switching)

**Critical design decision:** A user should NEVER "switch" roles. They should have **one identity** that can hold **multiple roles**, each unlocked through a distinct onboarding flow:

| Current Role | Upgrade To | Unlock Mechanism | Verification |
|-------------|-----------|-----------------|-------------|
| Guest (default) | — | Automatic on OTP login | Phone OTP |
| Guest | Club Owner | "Claim Your Club" flow | Business PAN + venue photos + manager PIN |
| Guest | PR Promoter | "Become a Verified PR" flow | Instagram handle + portfolio + venue sponsorship |
| Club Owner | Door Manager (sub-role) | Owner creates staff PIN | Owner-issued 6-digit PIN |
| PR Promoter | Sub-Promoter | Lead PR generates split link | Lead PR authorization |

**The UI should reflect this:**

```jsx
// CURRENT (Confusing): Role switcher in header
<select onChange={(e) => setRole(e.target.value)}>
  <option value="guest">Guest</option>
  <option value="owner">Club Owner</option>
  <option value="pr">PR Promoter</option>
</select>

// RECOMMENDED: Single identity with role-based navigation
const { user } = useAuth(); // { phone, roles: ['guest', 'pr'] }

<nav>
  <NavLink to="/events">Browse Events</NavLink>  {/* Always visible */}
  {user.roles.includes('pr') && (
    <NavLink to="/pr/dashboard">PR Console</NavLink>
  )}
  {user.roles.includes('owner') && (
    <NavLink to="/owner/gate">Gate Scanner</NavLink>
  )}
  <NavLink to="/profile">
    <img src={user.avatar} /> {user.name}
  </NavLink>
</nav>
```

---

## 3. Guest Experience Deep-Dive

### 3.1 Discovery & Filtering — What Works

The `GuestView.jsx` event browsing is **well-structured**:

- **City selector** (Mumbai, Goa, Delhi) persisted to localStorage
- **Genre filter pills** (All Vibes, Commercial EDM, Techno, Bollywood, etc.)
- **Search bar** filtering by event title, venue name, and genre
- **Event cards** with hero image, venue, date/time, lowest bid price, savings badge

**Guest Persona Verdict:** ✅ The discovery flow is clean. A partygoer can find tonight's events in their city within 2 seconds. The "Save up to ₹300" badge on event cards creates immediate value perception.

**Issue G2 Deep-Dive — PR Jargon Leaks:**

```jsx
// CURRENT (PromoterView language in GuestView):
<h3>Authorized Promoter Bids ({event.bids.length} Active Offers)</h3>
<p>Promoters compete to give you the lowest price and best perks.</p>

// RECOMMENDED (Guest-friendly language):
<h3>🎉 {event.bids.length} Exclusive VIP Deals Available</h3>
<p>Verified nightlife experts are offering you discounted entry + free perks.</p>
```

The word "Promoter" and "Bids" are industry jargon. A 23-year-old going out on Saturday night doesn't think in terms of "bids" — they think in terms of "deals" or "offers."

### 3.2 PR Bid Comparison — VIP Concierge vs. Confusion

The bid comparison cards in `EventDetailModal.jsx` show:
- PR avatar + name + verified badge
- Star rating + conversion count
- Price per pax + savings badge
- Bundled perks (free shooter, queue jump)
- PR pitch notes

**Guest Persona Verdict:** ⚠️ The information is valuable but overwhelming. A guest seeing "340+ check-ins" doesn't know if that's good or bad. The `bid.notes` field shows raw PR text like "VIP back-room access included" which is great, but the PR's `@handle` is unnecessary guest-facing information.

**Recommended Simplification:**

```jsx
// CURRENT: Shows PR internals
<div>
  <span className="font-bold">{pr.name}</span>
  <span>{pr.handle}</span>  // @arjun_nightlife — guest doesn't need this
  <span>{pr.conversions}+ check-ins</span>  // What does this mean to a guest?
</div>

// RECOMMENDED: Guest-centric value proposition
<div>
  <span className="font-bold">{pr.name}</span>
  {pr.verified && <VerifiedBadge />}
  <span>⭐ {pr.rating} · {pr.conversions}+ happy guests</span>
  <span className="savings">You save ₹{savings}</span>
</div>
```

### 3.3 Checkout Flow — Headcount → UPI → Dynamic Pass

**Step 1: Headcount Selection**

The male/female stepper is functional but has issues:
- **G3:** Stag-heavy warning is informational only — no price impact shown
- **G7:** Stepper buttons are 28px (below 44px WCAG minimum)
- **Missing:** No maximum pax enforcement per booking (a guest could book for 50 people)

**Step 2: UPI Payment**

```jsx
// CURRENT: Simulated payment methods
{[
  { id: 'UPI_GPAY', name: 'Google Pay', icon: '🟢' },
  { id: 'UPI_PHONEPE', name: 'PhonePe', icon: '🟣' },
  { id: 'UPI_PAYTM', name: 'Paytm UPI', icon: '🔵' },
  { id: 'CARDS', name: 'Credit / Debit', icon: '💳' },
]}
```

**Guest Persona Verdict:** 🔴 This is emoji-based fake payment. In production, this MUST be replaced with Razorpay Checkout SDK:

```jsx
// PRODUCTION: Real Razorpay integration
const handlePayment = async () => {
  // 1. Create order on backend
  const { order_id, amount } = await api.post('/api/passes/create-checkout', {
    eventId: event.id,
    prBidId: selectedBid.id,
    maleCount,
    femaleCount,
  });
  
  // 2. Open Razorpay Checkout
  const options = {
    key: import.meta.env.VITE_RAZORPAY_KEY_ID,
    amount: amount, // in paise
    currency: 'INR',
    order_id: order_id,
    name: 'NightVibe India',
    description: `${event.title} — ${totalPax} Guest Pass`,
    handler: async (response) => {
      // 3. Verify payment on backend
      await api.post('/api/passes/confirm-payment', {
        razorpay_order_id: response.razorpay_order_id,
        razorpay_payment_id: response.razorpay_payment_id,
        razorpay_signature: response.razorpay_signature,
      });
      // 4. Show dynamic pass
      onBookingSuccess(booking);
    },
    prefill: {
      name: user.name,
      email: user.email,
      contact: user.phone,
    },
    theme: { color: '#7C3AED' }, // Purple to match NightVibe brand
  };
  
  const rzp = new window.Razorpay(options);
  rzp.open();
};
```

**Step 3: Dynamic QR Pass**

The `MyPassesModal.jsx` rotating QR is the product's **crown jewel** — the 30-second TOTP rotation with the radar-line sweep animation is visually compelling and communicates security.

**Guest Persona Verdict:** ✅ The pass feels premium and secure. The countdown timer creates urgency. The "Anti-Screenshot Active" label builds trust.

**Critical Security Gap (S6):** The frontend generates the QR payload client-side:

```jsx
// CURRENT (INSECURE): Client-side QR generation
const dynamicPayload = JSON.stringify({
  tkt: selectedBooking.id,
  totp: totpNonce,                    // Client-generated nonce
  secHash: `${selectedBooking.qrToken}-${totpNonce}`,  // String concat, not HMAC
});
```

The `secHash` is just `qrToken-nonce` — not a cryptographic signature. Anyone who intercepts the `qrToken` (which is stored in localStorage) can generate valid QR codes indefinitely.

**The backend `security.py` has proper HMAC-SHA256, but it's never used by the frontend or the gate verification endpoint.**

---

## 4. Club Owner & Bouncer Experience

### 4.1 The Gate Scanner — Make or Break Feature

The `OwnerView.jsx` scanner tab is the **single most critical feature** for venue adoption. If this doesn't work flawlessly in a dark, loud, crowded club entrance at 11:30 PM on a Saturday, the entire platform fails.

**Venue GM Persona Verdict:** 🔴 The current scanner is a prototype mock, not a production tool.

**Issues:**

1. **V2: Client-side validation only.** `handleInspectTicket` reads from `bookings` state:
   ```jsx
   const found = bookings.find(
     (b) => b.id === targetId || b.qrToken === targetId || targetId.includes(b.id)
   );
   ```
   This means the scanner only works if the booking was made in the same browser session. Two different devices can't share booking data.

2. **V3: TOTP verification is bypassed.** The backend endpoint `verify-qr-totp` accepts the signature as optional:
   ```python
   class ScanTicketRequest(BaseModel):
       ticketId: str
       totpNonce: int
       signature: Optional[str] = None  # Optional! Never verified!
   ```
   And the verification logic only checks nonce drift, never calls `verify_totp_token()`:
   ```python
   current_nonce = int(datetime.datetime.utcnow().timestamp() // 30)
   if abs(req.totpNonce - current_nonce) > 1:
       return {"status": "EXPIRED_TOTP", ...}
   # Never verifies the HMAC signature!
   ```

3. **V4: No offline capability.** The scanner requires a live API connection. In basement venues (most Mumbai clubs), this is a dealbreaker.

**Recommended Gate Scanner Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    GATE SCANNER FLOW                         │
│                                                              │
│  Guest Phone                    Bouncer Tablet               │
│  ┌──────────┐                  ┌──────────────┐             │
│  │ Generate  │    QR Scan      │ Camera reads │             │
│  │ HMAC-SHA  │───────────────►│ QR payload   │             │
│  │ 256 TOTP  │                │              │             │
│  └──────────┘                 └──────┬───────┘             │
│                                      │                      │
│                                      ▼                      │
│                              ┌──────────────┐              │
│                              │ Local HMAC   │              │
│                              │ Verification │              │
│                              │ (< 50ms)     │              │
│                              └──────┬───────┘              │
│                                      │                      │
│                              ┌───────┴───────┐             │
│                              ▼               ▼             │
│                         ✅ VALID        ❌ INVALID          │
│                              │               │              │
│                              ▼               ▼             │
│                    ┌──────────────┐  ┌──────────────┐      │
│                    │ Show Guest   │  │ Red screen + │      │
│                    │ Green screen │  │ Error reason │      │
│                    │ + Haptic ✅  │  │ + Haptic ❌  │      │
│                    └──────┬───────┘  └──────────────┘      │
│                           │                                 │
│                           ▼                                 │
│                    ┌──────────────┐                         │
│                    │ ADMIT /      │                         │
│                    │ REJECT       │                         │
│                    │ buttons      │                         │
│                    └──────┬───────┘                         │
│                           │                                 │
│                           ▼ (when online)                   │
│                    ┌──────────────┐                         │
│                    │ POST /api/   │                         │
│                    │ escrow/      │                         │
│                    │ settle       │                         │
│                    └──────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Escrow Release Mechanics

**Current flow in `main.py`:**

```python
@app.post("/api/escrow/settle-admission")
def settle_admission(ticketId: str):
    # 1. Mark booking as ADMITTED
    booking["status"] = "ADMITTED"
    booking["escrowStatus"] = "SETTLED"
    
    # 2. Credit PR wallet (TDS 1% — should be 2%)
    tds = int(round(gross * 0.01))  # BUG: Should be 0.02 per Sec 194H
    promoter["walletInr"] += net_pr
```

**Venue GM Persona Verdict:** ⚠️ The escrow concept is correct (hold until scan), but the implementation has issues:

1. **TDS rate is wrong.** Code uses 1% (`gross * 0.01`) but Section 194H requires 2% (post-October 2024). The `models.py` EscrowLedger has `tds_1pct` as a column name, hardcoding the wrong rate into the schema.

2. **No two-step verification.** The strategy document (PROMPT2) correctly specifies "Step 1: Validate Scan → Step 2: Physical Admission (Admit)". But the current API has a single `settle-admission` endpoint that does both at once. There's no intermediate "validated, awaiting admission" state.

3. **No rolling reserve.** The strategy doc mentions "5-10% Club Rolling Reserve" for handling rejections and chargebacks. The current model has no reserve mechanism.

**Recommended Escrow Flow:**

```python
# PRODUCTION: Two-step escrow with proper TDS
@app.post("/api/gate/validate")
async def validate_scan(req: ScanTicketRequest):
    """Step 1: Verify QR authenticity. Does NOT release escrow."""
    booking = await db.get(BookingPass, req.ticketId)
    
    # Verify HMAC signature (REQUIRED, not optional)
    if not verify_totp_token(req.ticketId, req.totpNonce, req.signature):
        raise HTTPException(401, "Invalid QR signature. Possible screenshot fraud.")
    
    # Check venue match
    if booking.venue_id != req.venueId:
        raise HTTPException(403, "Pass not authorized for this venue")
    
    # Check duplicate
    if booking.status == BookingStatus.ADMITTED:
        raise HTTPException(409, "Pass already used")
    
    # Return guest details for bouncer review (DO NOT settle yet)
    return {
        "status": "VALIDATED",
        "guest": {
            "name": booking.guest_name,
            "pax": booking.pax,
            "male": booking.male_count,
            "female": booking.female_count,
            "perks": booking.perks,
        },
        "promoter": booking.promoter.name,
        "awaiting_admission": True,
    }

@app.post("/api/gate/admit")
async def admit_guest(ticketId: str, bouncer_id: str, photo_url: Optional[str] = None):
    """Step 2: Physical admission. NOW release escrow."""
    booking = await db.get(BookingPass, ticketId)
    
    # Must be validated first
    if booking.status != BookingStatus.VALIDATED:
        raise HTTPException(400, "Must validate scan before admission")
    
    # Mark admitted
    booking.status = BookingStatus.ADMITTED
    booking.scanned_at = datetime.utcnow()
    booking.scanned_by = bouncer_id
    
    # Settle escrow with correct TDS (2% u/s 194H)
    pr_gross = booking.promoter_payout
    tds_194h = round(pr_gross * 0.02)  # 2%, not 1%
    pr_net = pr_gross - tds_194h
    
    # Create ledger entry
    ledger = EscrowLedger(
        booking_id=booking.id,
        recipient_type="PROMOTER",
        recipient_id=booking.promoter_id,
        gross_amount_inr=pr_gross,
        tds_194h_2pct=tds_194h,  # Correct column name
        net_payout_inr=pr_net,
        status="SETTLED",
    )
    db.add(ledger)
    
    # Trigger Razorpay Payout API (not just wallet increment)
    await razorpay_payouts.create({
        "account_number": booking.promoter.upi_id,
        "amount": pr_net * 100,  # paise
        "currency": "INR",
        "mode": "UPI",
        "purpose": "commission",
    })
    
    await db.commit()
    return {"status": "ADMITTED", "pr_payout": pr_net}
```

### 4.3 PR Footfall Attribution Leaderboard

The `OwnerView.jsx` dashboard tab shows a PR leaderboard with:
- Admitted pax vs. booked pax
- Show-up rate percentage
- Gross revenue attributed

**Venue GM Persona Verdict:** ✅ This is exactly what club owners need. The ability to see which PRs are actually bringing bodies vs. ghost bookings is the platform's #1 value proposition for venues.

**Enhancement needed:** Add a "Revenue per Pax" column to identify high-spender PRs:

```jsx
// RECOMMENDED: Add spending quality metric
<td className="py-3 text-emerald-400 font-bold">
  ₹{Math.round(pr.grossRev / Math.max(1, pr.paxBrought))}/pax
</td>
```

### 4.4 GST + TDS Payout Reporting

**Current state:** The ledger tab shows transaction-level data but:
- No GST line item (18% on ticket, 18% on platform fee)
- TDS is 1% in code, should be 2%
- No Form 26Q / Form 16A generation
- No monthly GST summary (GSTR-8 for TCS)

**Venue GM Persona Verdict:** 🔴 This is a compliance liability. Club owners' chartered accountants will reject this ledger format. Need:

```jsx
// RECOMMENDED: GST-compliant ledger row
<tr>
  <td>{txn.id}</td>
  <td>{txn.eventTitle}</td>
  <td>₹{txn.grossAmount}</td>
  <td>₹{txn.ticketGst18Pct}</td>      {/* NEW: 18% GST on ticket */}
  <td>₹{txn.venueNet}</td>
  <td>₹{txn.prCommission}</td>
  <td>₹{txn.tds194h2Pct}</td>          {/* FIXED: 2% TDS */}
  <td>₹{txn.tds194o1Pct}</td>          {/* NEW: 1% TDS on venue payout */}
  <td>₹{txn.platformFee}</td>
  <td>₹{txn.platformGst18Pct}</td>     {/* NEW: 18% GST on platform fee */}
  <td className="text-emerald-400">SETTLED</td>
</tr>
```

---

## 5. PR Promoter Experience

### 5.1 PR Profile Creation

**Current state:** The `models.py` Promoter model has the right fields:

```python
class Promoter(Base):
    handle = Column(String, unique=True)     # @arjun_nightlife
    niche = Column(String, default="VIP Nightlife")
    tier = Column(String, default="Rising Star")
    rating = Column(Float, default=4.9)
    show_up_rate = Column(Integer, default=90)
    verified = Column(Boolean, default=False)
    upi_id = Column(String, nullable=False)
```

**PR Persona Verdict:** ⚠️ The data model is reasonable, but there's **no onboarding flow**. A PR can't sign up, submit their Instagram profile, request venue authorization, or get verified. They're pre-seeded in the database.

**Recommended PR Onboarding Flow:**

```
┌─────────────────────────────────────────────────────────────┐
│                 PR ONBOARDING (4 screens)                    │
│                                                              │
│  Screen 1: "Join as a Nightlife Expert"                     │
│  ├── Phone OTP (already authenticated)                      │
│  ├── Full name                                              │
│  ├── Instagram handle (for verification)                    │
│  └── City (Mumbai / Goa / Delhi / Bangalore)                │
│                                                              │
│  Screen 2: "Your Expertise"                                 │
│  ├── Niche selector (VIP Tables / Guestlist / Corporate)    │
│  ├── Venues you currently work with (multi-select)          │
│  ├── Average weekly guests you bring                        │
│  └── Upload portfolio (3-5 club night photos)               │
│                                                              │
│  Screen 3: "Get Paid Instantly"                             │
│  ├── UPI ID (auto-verified via ₹1 test transaction)         │
│  ├── PAN number (for TDS compliance)                        │
│  └── Bank account (fallback for IMPS)                       │
│                                                              │
│  Screen 4: "Verification Pending"                           │
│  ├── Status: "We'll verify your Instagram within 24 hours"  │
│  ├── Meanwhile: Browse events (read-only)                   │
│  └── Notification when verified + first venue authorized    │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Dynamic Bidding Engine

The `PromoterView.jsx` bidding console is the **most polished feature** in the prototype:

- **Event selector** (filtered by authorized venues)
- **Price slider** bounded by `floorPrice` and `basePrice`
- **Perk bundling** from venue-approved perks list
- **Custom pitch notes**
- **Live commission calculator** showing gross, TDS, and net payout

**PR Persona Verdict:** ✅ The bidding UX is excellent. The price slider with floor/ceiling bounds prevents accidental underpricing. The live commission calculator builds trust by showing exactly what the PR will earn.

**Issues:**

1. **P5: Commission formula opacity:**
   ```jsx
   // CURRENT: Magic numbers
   const estimatedGrossCommission = Math.max(150, discountGiven + 120);
   // Where does 150 and 120 come from?
   
   // RECOMMENDED: Transparent formula
   const baseCommission = event.commissionCap * 0.4; // 40% of cap as base
   const discountBonus = discountGiven * 0.5; // 50% of discount given
   const estimatedGrossCommission = Math.max(
     MIN_COMMISSION, // ₹150 floor (explain this)
     baseCommission + discountBonus
   );
   ```

2. **P3: No bid cooldown:**
   ```jsx
   // RECOMMENDED: Add cooldown to submitPRBid
   const submitPRBid = (eventId, prId, price, perks, notes) => {
     const lastBid = getLastBidTime(prId, eventId);
     const cooldownMs = 15 * 60 * 1000; // 15 minutes
     
     if (lastBid && Date.now() - lastBid < cooldownMs) {
       const remaining = Math.ceil((cooldownMs - (Date.now() - lastBid)) / 60000);
       showToast(`⏱️ Bid cooldown: Wait ${remaining} minutes before updating`, 'warning');
       return;
     }
     
     // Check if event is within 2 hours (bidding locked)
     if (isWithinHours(event.startTime, 2)) {
       showToast('🔒 Bidding locked 2 hours before event start', 'warning');
       return;
     }
     
     // Proceed with bid submission
   };
   ```

3. **P4: No competitor visibility:**
   ```jsx
   // RECOMMENDED: Anonymous competitor stats
   <div className="p-3 rounded-xl bg-white/5 border border-white/10">
     <h4 className="text-xs font-bold text-slate-300">Market Intelligence</h4>
     <div className="grid grid-cols-3 gap-2 mt-2 text-center">
       <div>
         <span className="text-[10px] text-slate-400 block">Lowest Bid</span>
         <span className="text-sm font-bold text-emerald-400">₹{lowestBid}</span>
       </div>
       <div>
         <span className="text-[10px] text-slate-400 block">Average Bid</span>
         <span className="text-sm font-bold text-amber-400">₹{avgBid}</span>
       </div>
       <div>
         <span className="text-[10px] text-slate-400 block">Your Rank</span>
         <span className="text-sm font-bold text-cyan-400">#{yourRank}/{totalBids}</span>
       </div>
     </div>
   </div>
   ```

### 5.3 PR Wallet & Instant UPI Withdrawal

**Current state:** The wallet shows `unlockedEarnings` (sum of post-TDS commissions from scanned bookings) and `pendingEscrow` (sum of pre-scan commissions). The "Instant UPI Withdrawal" button fires confetti and shows a toast.

**PR Persona Verdict:** 🔴 The wallet UI is perfect. The withdrawal is fake. In production:

```python
# PRODUCTION: Real UPI payout via Razorpay Payouts API
@app.post("/api/pr/withdraw")
async def withdraw_to_upi(pr_id: str, amount: int):
    promoter = await db.get(Promoter, pr_id)
    
    # Validate sufficient balance
    if promoter.unlocked_wallet_inr < amount:
        raise HTTPException(400, "Insufficient unlocked balance")
    
    # Minimum withdrawal ₹100
    if amount < 100:
        raise HTTPException(400, "Minimum withdrawal is ₹100")
    
    # Create Razorpay Payout
    payout = razorpay_payout.create({
        "account_number": RAZORPAY_ACCOUNT,
        "fund_account_id": promoter.razorpay_fund_account_id,
        "amount": amount * 100,  # paise
        "currency": "INR",
        "mode": "UPI",
        "purpose": "commission",
        "queue_if_low_balance": True,
    })
    
    # Deduct from wallet
    promoter.unlocked_wallet_inr -= amount
    
    # Record payout
    payout_record = PayoutRecord(
        promoter_id=pr_id,
        amount_inr=amount,
        razorpay_payout_id=payout["id"],
        status="PROCESSING",
    )
    db.add(payout_record)
    await db.commit()
    
    return {"status": "PROCESSING", "payout_id": payout["id"]}
```

### 5.4 PR Tier Progression

**Current state:** `models.py` has `tier = Column(String, default="Rising Star")` but no computed progression.

**Recommended Tier System:**

```python
# PRODUCTION: Algorithmic tier computation
TIERS = {
    "Rising Star": {"min_score": 0, "max_score": 29, "commission_boost": 0, "color": "slate"},
    "Silver":      {"min_score": 30, "max_score": 59, "commission_boost": 0.05, "color": "gray"},
    "Gold":        {"min_score": 60, "max_score": 79, "commission_boost": 0.10, "color": "amber"},
    "Platinum":    {"min_score": 80, "max_score": 89, "commission_boost": 0.15, "color": "cyan"},
    "Elite Black": {"min_score": 90, "max_score": 100, "commission_boost": 0.20, "color": "purple"},
}

def compute_pr_tier(promoter, bookings):
    """Compute tier based on weighted performance metrics."""
    pr_bookings = [b for b in bookings if b.promoter_id == promoter.id]
    scanned = [b for b in pr_bookings if b.status == "ADMITTED"]
    
    # Show-up rate (40% weight)
    show_up = len(scanned) / max(1, len(pr_bookings))
    
    # Volume score (20% weight) — normalized against city median
    volume = min(1.0, len(scanned) / 50)  # 50 pax = max volume score
    
    # Rating (25% weight) — Bayesian smoothed
    avg_rating = sum(b.guest_rating or 4 for b in scanned) / max(1, len(scanned))
    rating_score = (len(scanned) * (avg_rating / 5) + 8 * 0.75) / (len(scanned) + 8)
    
    # Consistency (15% weight) — weeks active
    weeks_active = len(set(b.created_at.isocalendar()[1] for b in pr_bookings))
    consistency = min(1.0, weeks_active / 12)
    
    composite = (
        0.40 * show_up +
        0.20 * volume +
        0.25 * rating_score +
        0.15 * consistency
    ) * 100
    
    for tier_name, tier_config in TIERS.items():
        if tier_config["min_score"] <= composite <= tier_config["max_score"]:
            return tier_name, round(composite, 1)
    
    return "Rising Star", round(composite, 1)
```

---

## 6. Direct Mobile OTP Architecture Spec

### 6.1 Backend: FastAPI + MSG91 OTP + JWT

```python
# backend/auth.py

import os
import time
import httpx
import jwt
import redis
from fastapi import FastAPI, HTTPException, Depends, Cookie
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from typing import Optional

# ─── CONFIG ───────────────────────────────────────────────────────

MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY")  # From msg91.com
MSG91_TEMPLATE_ID = os.getenv("MSG91_TEMPLATE_ID")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 7 * 24 * 3600  # 7 days

redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

# ─── SCHEMAS ──────────────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    phone: str  # +919876543210

class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str

class TokenResponse(BaseModel):
    access_token: str
    user: dict

# ─── OTP SERVICE (MSG91) ─────────────────────────────────────────

async def send_otp_msg91(phone: str) -> dict:
    """Send OTP via MSG91 Transactional SMS API."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://control.msg91.com/api/v5/otp",
            headers={
                "authkey": MSG91_AUTH_KEY,
                "Content-Type": "application/json",
            },
            json={
                "template_id": MSG91_TEMPLATE_ID,
                "mobile": phone,  # e.g., "919876543210" (no +)
                "otp_expiry": 5,  # 5 minutes
            },
        )
        data = response.json()
        if data.get("type") == "success":
            return {"status": "SENT", "request_id": data["request_id"]}
        raise HTTPException(400, f"OTP send failed: {data.get('message')}")

async def verify_otp_msg91(phone: str, otp: str) -> bool:
    """Verify OTP via MSG91."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://control.msg91.com/api/v5/otp/verify",
            params={"authkey": MSG91_AUTH_KEY, "mobile": phone, "otp": otp},
        )
        data = response.json()
        return data.get("type") == "success"

# ─── JWT TOKEN MANAGEMENT ────────────────────────────────────────

def create_jwt(user_id: str, phone: str, roles: list) -> str:
    payload = {
        "sub": user_id,
        "phone": phone,
        "roles": roles,  # ['guest'], ['guest', 'pr'], ['guest', 'owner']
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")

# ─── AUTH DEPENDENCY ──────────────────────────────────────────────

security = HTTPBearer(auto_error=False)

async def get_current_user(
    authorization: Optional[str] = Depends(security),
    session_token: Optional[str] = Cookie(None),
) -> dict:
    """Extract user from Bearer token or session cookie."""
    token = None
    if authorization:
        token = authorization.credentials
    elif session_token:
        token = session_token
    
    if not token:
        raise HTTPException(401, "Authentication required")
    
    return decode_jwt(token)

async def require_role(role: str):
    """Dependency factory for role-based access control."""
    async def checker(user: dict = Depends(get_current_user)):
        if role not in user.get("roles", []):
            raise HTTPException(403, f"Role '{role}' required. Your roles: {user['roles']}")
        return user
    return checker

# ─── RATE LIMITING ────────────────────────────────────────────────

def check_rate_limit(phone: str, action: str, max_attempts: int = 5, window: int = 300):
    """Rate limit: max_attempts per window seconds per phone+action."""
    key = f"ratelimit:{action}:{phone}"
    attempts = redis_client.get(key)
    
    if attempts and int(attempts) >= max_attempts:
        raise HTTPException(429, f"Too many {action} attempts. Try again in {window // 60} minutes.")
    
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, window)
    pipe.execute()

# ─── AUTH ROUTES ──────────────────────────────────────────────────

@app.post("/api/auth/send-otp")
async def auth_send_otp(req: SendOTPRequest):
    """Step 1: Send OTP to Indian mobile number."""
    # Validate Indian phone format
    phone = req.phone.replace("+", "").replace(" ", "")
    if not phone.startswith("91") or len(phone) != 12:
        raise HTTPException(400, "Invalid Indian phone number. Use +91XXXXXXXXXX")
    
    # Rate limit: 5 OTPs per 5 minutes
    check_rate_limit(phone, "send_otp", max_attempts=5, window=300)
    
    # Send via MSG91
    result = await send_otp_msg91(phone)
    
    # Store request_id for verification
    redis_client.setex(f"otp_request:{phone}", 300, result["request_id"])
    
    return {"status": "OTP_SENT", "phone": phone[-4:].rjust(len(phone), "*")}

@app.post("/api/auth/verify-otp", response_model=TokenResponse)
async def auth_verify_otp(req: VerifyOTPRequest):
    """Step 2: Verify OTP and issue JWT."""
    phone = req.phone.replace("+", "").replace(" ", "")
    
    # Rate limit: 10 verification attempts per 5 minutes
    check_rate_limit(phone, "verify_otp", max_attempts=10, window=300)
    
    # Verify with MSG91
    is_valid = await verify_otp_msg91(phone, req.otp)
    if not is_valid:
        raise HTTPException(401, "Invalid or expired OTP")
    
    # Find or create user
    user = await db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(
            phone=phone,
            name=f"Guest {phone[-4:]}",
            roles=["guest"],  # Default role
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    
    # Issue JWT
    token = create_jwt(str(user.id), phone, user.roles)
    
    return {
        "access_token": token,
        "user": {
            "id": str(user.id),
            "phone": phone,
            "name": user.name,
            "roles": user.roles,
            "avatar": user.avatar_url,
        },
    }

# ─── ROLE UPGRADE ROUTES ─────────────────────────────────────────

@app.post("/api/auth/upgrade-to-pr")
async def upgrade_to_pr(
    req: PRUpgradeRequest,
    user: dict = Depends(get_current_user),
):
    """Upgrade guest to PR promoter role via onboarding submission."""
    if "pr" in user["roles"]:
        raise HTTPException(400, "Already a PR promoter")
    
    # Create promoter profile
    promoter = Promoter(
        user_id=user["sub"],
        name=req.name,
        handle=f"@{req.instagram_handle}",
        niche=req.niche,
        city=req.city,
        upi_id=req.upi_id,
        phone=user["phone"],
        verified=False,  # Pending manual verification
        tier="Rising Star",
    )
    db.add(promoter)
    
    # Add 'pr' role to user
    await db.execute(
        User.update().where(User.id == user["sub"]).values(
            roles=User.roles + ["pr"]
        )
    )
    await db.commit()
    
    # Issue new JWT with updated roles
    new_token = create_jwt(user["sub"], user["phone"], user["roles"] + ["pr"])
    
    return {
        "status": "UPGRADED",
        "access_token": new_token,
        "message": "PR profile created. Verification pending within 24 hours.",
    }

@app.post("/api/auth/upgrade-to-owner")
async def upgrade_to_owner(
    req: OwnerUpgradeRequest,
    user: dict = Depends(get_current_user),
):
    """Upgrade guest to club owner via venue claim flow."""
    if "owner" in user["roles"]:
        raise HTTPException(400, "Already a club owner")
    
    # Verify venue claim PIN (issued by NightVibe sales team)
    venue = await db.query(Venue).filter(Venue.claim_pin == req.claim_pin).first()
    if not venue:
        raise HTTPException(400, "Invalid venue claim PIN. Contact NightVibe sales.")
    
    # Link user to venue
    owner_profile = OwnerProfile(user_id=user["sub"])
    db.add(owner_profile)
    venue.owner_id = user["sub"]
    
    # Add 'owner' role
    await db.execute(
        User.update().where(User.id == user["sub"]).values(
            roles=User.roles + ["owner"]
        )
    )
    await db.commit()
    
    new_token = create_jwt(user["sub"], user["phone"], user["roles"] + ["owner"])
    
    return {
        "status": "UPGRADED",
        "access_token": new_token,
        "venue": {"id": venue.id, "name": venue.name},
    }
```

### 6.2 Frontend: React Auth Context + OTP Flow

```jsx
// src/context/AuthContext.jsx

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext();

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.nightvibe.in';

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('nv_token'));
  const [loading, setLoading] = useState(true);

  // Verify token on mount
  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    
    fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(res => res.ok ? res.json() : Promise.reject())
      .then(data => {
        setUser(data.user);
        setLoading(false);
      })
      .catch(() => {
        localStorage.removeItem('nv_token');
        setToken(null);
        setLoading(false);
      });
  }, [token]);

  const sendOTP = useCallback(async (phone) => {
    const res = await fetch(`${API_BASE}/api/auth/send-otp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone }),
    });
    if (!res.ok) throw new Error((await res.json()).detail);
    return res.json();
  }, []);

  const verifyOTP = useCallback(async (phone, otp) => {
    const res = await fetch(`${API_BASE}/api/auth/verify-otp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, otp }),
    });
    if (!res.ok) throw new Error((await res.json()).detail);
    const data = await res.json();
    
    localStorage.setItem('nv_token', data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    return data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('nv_token');
    setToken(null);
    setUser(null);
  }, []);

  const hasRole = useCallback((role) => {
    return user?.roles?.includes(role) ?? false;
  }, [user]);

  return (
    <AuthContext.Provider value={{ user, token, loading, sendOTP, verifyOTP, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
```

```jsx
// src/components/auth/PhoneOTPLogin.jsx

import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Phone, ShieldCheck, ArrowRight, Loader2 } from 'lucide-react';

export const PhoneOTPLogin = ({ onSuccess }) => {
  const { sendOTP, verifyOTP } = useAuth();
  
  const [step, setStep] = useState('phone'); // 'phone' | 'otp'
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  
  const otpRefs = useRef([]);

  // Cooldown timer for resend
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => setCooldown(c => c - 1), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  const handleSendOTP = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    
    try {
      const formatted = phone.startsWith('+91') ? phone : `+91${phone}`;
      await sendOTP(formatted);
      setStep('otp');
      setCooldown(30);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleOTPChange = (index, value) => {
    if (!/^\d?$/.test(value)) return;
    
    const newOtp = [...otp];
    newOtp[index] = value;
    setOtp(newOtp);
    
    // Auto-advance to next input
    if (value && index < 5) {
      otpRefs.current[index + 1]?.focus();
    }
    
    // Auto-submit when all 6 digits entered
    if (newOtp.every(d => d !== '') && newOtp.join('').length === 6) {
      handleVerifyOTP(newOtp.join(''));
    }
  };

  const handleOTPKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !otp[index] && index > 0) {
      otpRefs.current[index - 1]?.focus();
    }
  };

  const handleVerifyOTP = async (otpString) => {
    setError('');
    setLoading(true);
    
    try {
      const formatted = phone.startsWith('+91') ? phone : `+91${phone}`;
      await verifyOTP(formatted, otpString);
      onSuccess?.();
    } catch (err) {
      setError(err.message);
      setOtp(['', '', '', '', '', '']);
      otpRefs.current[0]?.focus();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#090a0f]">
      <div className="w-full max-w-sm space-y-8">
        
        {/* Brand */}
        <div className="text-center space-y-2">
          <div className="text-4xl">🍸</div>
          <h1 className="text-2xl font-black text-white">NightVibe India</h1>
          <p className="text-sm text-slate-400">
            {step === 'phone' 
              ? 'Enter your mobile number to get started'
              : `OTP sent to +91 ${phone.slice(-4).padStart(phone.length, '*')}`
            }
          </p>
        </div>

        {step === 'phone' ? (
          <form onSubmit={handleSendOTP} className="space-y-4">
            <div className="relative">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-sm font-semibold">
                +91
              </span>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(0, 10))}
                placeholder="98765 43210"
                autoFocus
                className="w-full pl-14 pr-4 py-4 rounded-2xl bg-white/5 border border-white/10 
                           text-white text-lg font-mono tracking-wider
                           focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 focus:outline-none
                           placeholder:text-slate-600"
              />
            </div>
            
            {error && <p className="text-xs text-rose-400 text-center">{error}</p>}
            
            <button
              type="submit"
              disabled={phone.length !== 10 || loading}
              className="w-full py-4 rounded-2xl bg-gradient-to-r from-purple-600 to-pink-600 
                         hover:from-purple-500 hover:to-pink-500
                         disabled:opacity-40 disabled:cursor-not-allowed
                         text-white text-sm font-bold shadow-xl shadow-purple-600/30 
                         transition flex items-center justify-center gap-2"
            >
              {loading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <>
                  <Phone className="w-4 h-4" />
                  <span>Send OTP</span>
                </>
              )}
            </button>
          </form>
        ) : (
          <div className="space-y-6">
            {/* 6-digit OTP input */}
            <div className="flex items-center justify-center gap-2">
              {otp.map((digit, i) => (
                <input
                  key={i}
                  ref={el => otpRefs.current[i] = el}
                  type="tel"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleOTPChange(i, e.target.value)}
                  onKeyDown={(e) => handleOTPKeyDown(i, e)}
                  autoFocus={i === 0}
                  className="w-12 h-14 rounded-xl bg-white/5 border border-white/10 
                             text-white text-xl font-bold text-center
                             focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 focus:outline-none
                             transition"
                />
              ))}
            </div>
            
            {error && <p className="text-xs text-rose-400 text-center">{error}</p>}
            
            {/* Resend OTP */}
            <div className="text-center">
              {cooldown > 0 ? (
                <span className="text-xs text-slate-500">Resend OTP in {cooldown}s</span>
              ) : (
                <button
                  onClick={() => { setStep('phone'); setCooldown(0); }}
                  className="text-xs text-purple-400 hover:text-purple-300 font-medium"
                >
                  Change number or resend OTP
                </button>
              )}
            </div>
            
            {loading && (
              <div className="flex items-center justify-center gap-2 text-xs text-purple-300">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Verifying...</span>
              </div>
            )}
          </div>
        )}
        
        {/* Trust signals */}
        <div className="flex items-center justify-center gap-4 text-[10px] text-slate-500">
          <span className="flex items-center gap-1">
            <ShieldCheck className="w-3 h-3" /> 256-bit Encrypted
          </span>
          <span>•</span>
          <span>RBI Compliant</span>
          <span>•</span>
          <span>Zero Spam SMS</span>
        </div>
      </div>
    </div>
  );
};
```

### 6.3 App-Level Route Gating

```jsx
// src/App.jsx (refactored)

import { useAuth } from './context/AuthContext';
import { PhoneOTPLogin } from './components/auth/PhoneOTPLogin';
import { RoleRouter } from './components/common/RoleRouter';

export const App = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return <SplashScreen />;
  }

  if (!user) {
    return <PhoneOTPLogin />;
  }

  // User is authenticated — route based on roles
  return <RoleRouter />;
};

// src/components/common/RoleRouter.jsx
export const RoleRouter = () => {
  const { user, hasRole } = useAuth();
  const [activeView, setActiveView] = useState('guest'); // Default to guest

  return (
    <div className="min-h-screen flex flex-col bg-[#090a0f] text-slate-100">
      <Header
        activeView={activeView}
        onViewChange={setActiveView}
        availableViews={[
          { id: 'guest', label: 'Browse Events', icon: '🎵', always: true },
          ...(hasRole('pr') ? [{ id: 'pr', label: 'PR Console', icon: '📊' }] : []),
          ...(hasRole('owner') ? [{ id: 'owner', label: 'Gate Scanner', icon: '📱' }] : []),
        ]}
      />
      
      <main className="flex-1">
        {activeView === 'guest' && <GuestView />}
        {activeView === 'pr' && hasRole('pr') && <PromoterView />}
        {activeView === 'owner' && hasRole('owner') && <OwnerView />}
      </main>
    </div>
  );
};
```

---

## 7. Production Migration Roadmap

### Phase 0: Foundation (Week 1-2)

| Task | Files | Description |
|------|-------|-------------|
| Initialize Vite + React 19 + Tailwind v4 | `package.json`, `vite.config.ts`, `tailwind.config.ts` | Replace Create React App with Vite. Upgrade to React 19 concurrent features. |
| Setup FastAPI project structure | `backend/`, `alembic/`, `requirements.txt` | Proper Python package structure with Alembic migrations |
| PostgreSQL + Prisma/SQLAlchemy setup | `backend/models.py`, `alembic/` | Replace in-memory `DB_STATE` with real database |
| Redis setup for caching & rate limiting | `backend/redis_client.py` | Session store, rate limits, live occupancy counters |
| Environment variable management | `.env.example`, `backend/config.py` | Move all secrets out of source code |

### Phase 1: Authentication & Identity (Week 2-3)

| Task | Files | Description |
|------|-------|-------------|
| MSG91 OTP integration | `backend/auth.py` | Phone OTP send/verify with rate limiting |
| JWT session management | `backend/auth.py`, `src/context/AuthContext.jsx` | Token issuance, refresh, role claims |
| React auth flow | `src/components/auth/PhoneOTPLogin.jsx` | 6-digit OTP input with auto-submit |
| Role-based routing | `src/components/common/RoleRouter.jsx` | Guest default, PR/Owner upgrade flows |
| PR onboarding flow | `src/components/auth/PROnboarding.jsx` | 4-screen wizard with Instagram verification |
| Club claim flow | `src/components/auth/ClubClaimFlow.jsx` | Venue PIN verification for owners |

### Phase 2: Payments & Escrow (Week 3-4)

| Task | Files | Description |
|------|-------|-------------|
| Razorpay Order creation | `backend/payments.py` | Create order, return order_id to frontend |
| Razorpay Checkout SDK | `src/components/guest/EventDetailModal.jsx` | Replace emoji payment buttons with real SDK |
| Razorpay webhook handler | `backend/webhooks.py` | Verify signature, update booking status |
| Razorpay Route split | `backend/payments.py` | Split payment: venue nodal + PR holdback + platform |
| Two-step gate admission | `backend/gate.py` | Validate → Admit → Settle escrow |
| Razorpay Payouts API | `backend/payouts.py` | Instant UPI payout to PR on admission |
| GST/TDS calculation | `backend/tax.py` | 18% GST, 2% TDS 194H, 1% TDS 194O |

### Phase 3: Gate Security (Week 4-5)

| Task | Files | Description |
|------|-------|-------------|
| HMAC-SHA256 QR generation | `backend/security.py` | Per-booking secret key, server-side signing |
| Frontend QR from server | `src/components/guest/MyPassesModal.jsx` | Fetch signed QR payload from API, not client-side |
| Gate scanner PWA | `src/components/owner/GateScannerPWA.jsx` | Offline-capable scanner with Service Worker |
| IndexedDB manifest cache | `src/sw/manifest-sync.js` | Pre-event sync of encrypted ticket manifest |
| Audio + haptic feedback | `src/utils/scanFeedback.js` | Web Audio tones + navigator.vibrate for 110dB environments |
| FLAG_SECURE (Android) | `android/app/src/main/AndroidManifest.xml` | Prevent screenshots on native wrapper |

### Phase 4: Real-Time & Polish (Week 5-6)

| Task | Files | Description |
|------|-------|-------------|
| WebSocket bid updates | `backend/websocket.py`, `src/hooks/useBidStream.js` | Real-time bid ranking changes |
| Redis occupancy counters | `backend/redis_client.py` | INCR/DECR on admit/reject, push via WebSocket |
| Dynamic floor pricing | `backend/pricing.py` | Capacity-responsive floor price computation |
| PR trust score algorithm | `backend/trust_score.py` | Geometric mean with Bayesian shrinkage |
| Design token system | `tailwind.config.ts` | Unified type scale, color tokens, spacing |
| Accessibility audit | All components | 44px touch targets, focus traps, ARIA labels |

### Phase 5: Compliance & Launch (Week 6-8)

| Task | Files | Description |
|------|-------|-------------|
| GST invoice generation | `backend/invoicing.py` | Dual-supply invoices (club + platform) |
| Form 26Q/16A generation | `backend/compliance.py` | Quarterly TDS filing automation |
| GSTR-8 TCS reporting | `backend/compliance.py` | Monthly TCS filing |
| PAN validation (Protean) | `backend/kyc.py` | Section 206AB non-filer check |
| Chargeback evidence bundles | `backend/disputes.py` | Auto-compile QR logs, timestamps, photos |
| Production deployment | `docker-compose.yml`, `k8s/` | Containerized deployment with health checks |

---

## 8. Git Delivery Guidelines

### 8.1 Branch Strategy

```
main                                    ← Production-ready code
├── feat/auth-otp-login                 ← Phase 1: Phone OTP auth
├── feat/razorpay-integration           ← Phase 2: Real payments
├── feat/gate-security-hmac             ← Phase 3: HMAC QR + offline scanner
├── feat/realtime-websocket             ← Phase 4: WebSocket + Redis
├── feat/compliance-gst-tds             ← Phase 5: Tax compliance
└── fix/totp-verification-bypass        ← Critical security fix (S6)
```

### 8.2 File-by-File Patch Instructions

#### Patch 1: Fix TOTP Verification Bypass (Critical Security Fix)

**File:** `backend/main.py`  
**Lines:** 120-130 (verify-qr-totp endpoint)

```python
# BEFORE (VULNERABLE):
@app.post("/api/passes/verify-qr-totp")
def verify_gate_qr(req: ScanTicketRequest):
    booking = next((b for b in DB_STATE["bookings"] if b["id"] == req.ticketId), None)
    if not booking:
        return {"status": "INVALID", "reason": "Ticket ID not found in system"}
    if booking["status"] == "ADMITTED":
        return {"status": "ALREADY_USED", ...}
    if booking["venueId"] != req.venueId:
        return {"status": "WRONG_VENUE", ...}
    # BUG: Only checks nonce drift, never verifies HMAC signature
    current_nonce = int(datetime.datetime.utcnow().timestamp() // 30)
    if abs(req.totpNonce - current_nonce) > 1:
        return {"status": "EXPIRED_TOTP", ...}
    return {"status": "ACTIVE", "booking": booking, ...}

# AFTER (SECURE):
@app.post("/api/passes/verify-qr-totp")
def verify_gate_qr(req: ScanTicketRequest):
    booking = next((b for b in DB_STATE["bookings"] if b["id"] == req.ticketId), None)
    if not booking:
        return {"status": "INVALID", "reason": "Ticket ID not found in system"}
    if booking["status"] == "ADMITTED":
        return {"status": "ALREADY_USED", ...}
    if booking["venueId"] != req.venueId:
        return {"status": "WRONG_VENUE", ...}
    
    # CRITICAL FIX: Verify HMAC signature (REQUIRED field)
    if not req.signature:
        return {"status": "INVALID_SIGNATURE", "reason": "QR signature missing. Possible screenshot."}
    
    is_valid = verify_totp_token(
        ticket_id=req.ticketId,
        provided_nonce=req.totpNonce,
        provided_signature=req.signature,
        secret_key=booking.get("qr_secret", SECRET_MASTER_KEY),
    )
    if not is_valid:
        return {"status": "INVALID_SIGNATURE", "reason": "QR token invalid or expired. Refresh your pass."}
    
    return {"status": "ACTIVE", "booking": booking, ...}
```

#### Patch 2: Fix CORS Configuration

**File:** `backend/main.py`  
**Lines:** 12-18

```python
# BEFORE (INSECURE):
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AFTER (SECURE):
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

#### Patch 3: Fix TDS Rate (1% → 2%)

**File:** `backend/main.py`  
**Lines:** ~130 (settle-admission)

```python
# BEFORE (WRONG):
tds = int(round(gross * 0.01))  # 1% — incorrect

# AFTER (CORRECT):
tds = int(round(gross * 0.02))  # 2% u/s 194H (Finance Act 2024)
```

**File:** `backend/models.py`  
**Line:** EscrowLedger class

```python
# BEFORE:
tds_1pct = Column(Integer, default=0)

# AFTER:
tdds_194h_2pct = Column(Integer, default=0)  # 2% TDS on PR commission
tds_194o_1pct = Column(Integer, default=0)   # 1% TDS on venue payout
```

#### Patch 4: Move Secret Key to Environment

**File:** `backend/security.py`  
**Line:** 5

```python
# BEFORE (HARDCODED):
SECRET_MASTER_KEY = "nightvibe_super_secret_master_key_2026"

# AFTER (ENVIRONMENT):
SECRET_MASTER_KEY = os.getenv("NIGHTVIBE_HMAC_SECRET")
if not SECRET_MASTER_KEY:
    raise RuntimeError("NIGHTVIBE_HMAC_SECRET environment variable is required")
```

#### Patch 5: Fix Ticket ID Entropy

**File:** `backend/main.py`  
**Line:** ~85

```python
# BEFORE (LOW ENTROPY — 16 bits):
ticket_id = f"TKT-{uuid.uuid4().hex[:4].upper()}"

# AFTER (HIGH ENTROPY — 80 bits):
import secrets
ticket_id = f"TKT-{secrets.token_hex(10).upper()}"  # e.g., TKT-A1B2C3D4E5F6G7H8I9J0
```

#### Patch 6: Add Rate Limiting Middleware

**File:** `backend/main.py`  
**New import + middleware:**

```python
from fastapi import Request
from fastapi.responses import JSONResponse
import redis

redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Rate limit API endpoints
    if request.url.path.startswith("/api/"):
        client_ip = request.client.host
        key = f"ratelimit:ip:{client_ip}"
        
        current = redis_client.get(key)
        if current and int(current) > 100:  # 100 requests per minute
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )
        
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)
        pipe.execute()
    
    return await call_next(request)
```

#### Patch 7: Add Razorpay Webhook Signature Verification

**File:** `backend/main.py`  
**Lines:** ~145 (razorpay_webhook)

```python
# BEFORE (NO VERIFICATION):
@app.post("/api/webhooks/razorpay")
def razorpay_webhook(payload: dict):
    event_type = payload.get("event")
    if event_type == "payment.captured":
        ...
    return {"status": "IGNORED"}

# AFTER (WITH SIGNATURE VERIFICATION):
import hmac
import hashlib

RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

@app.post("/api/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    
    # Verify webhook signature
    expected = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Invalid webhook signature")
    
    payload = json.loads(body)
    event_type = payload.get("event")
    
    if event_type == "payment.captured":
        payment = payload["payload"]["payment"]["entity"]
        order_id = payment["order_id"]
        payment_id = payment["id"]
        
        # Update booking with payment confirmation
        booking = await db.query(BookingPass).filter(
            BookingPass.razorpay_order_id == order_id
        ).first()
        
        if booking:
            booking.razorpay_payment_id = payment_id
            booking.status = BookingStatus.ACTIVE
            booking.escrow_status = EscrowStatus.HELD_IN_ESCROW
            await db.commit()
        
        return {"status": "PROCESSED"}
    
    return {"status": "IGNORED"}
```

### 8.3 Commit Message Convention

```
feat(auth): implement +91 phone OTP login with MSG91 integration
fix(security): verify HMAC signature in gate QR validation endpoint
fix(tax): correct TDS rate from 1% to 2% per Section 194H
refactor(context): extract booking logic into domain service
chore(deps): add razorpay, redis, httpx to requirements.txt
docs(readme): add production deployment guide
```

### 8.4 Recommended First PR

**Branch:** `fix/critical-security-patches`  
**Target:** `main`  
**Title:** `fix: patch 7 critical security vulnerabilities in backend`

**Files changed:**
1. `backend/security.py` — Move secret to env var
2. `backend/main.py` — Fix TOTP verification, CORS, TDS rate, ticket entropy, rate limiting, webhook verification
3. `backend/models.py` — Rename TDS column to reflect correct rate
4. `.env.example` — Add all required environment variables
5. `requirements.txt` — Add `redis`, `httpx`, `python-jose`

---

## Appendix: Complete Persona Journey Maps

### Guest Journey (Happy Path)
```
Open App → See Login → Enter +91 number → Receive OTP → Enter 6 digits → 
JWT issued (role: guest) → Browse events in Mumbai → Filter by "Commercial EDM" → 
See "Sunburn Arena" card with "Save up to ₹300" badge → Tap "Compare PR Bids" → 
See 3 VIP deals with prices, perks, ratings → Select Arjun's deal (₹1,700/pax + free shooter) → 
Set headcount (2M + 2F) → See total ₹7,140 (incl. fee) → Tap "Pay with UPI" → 
Razorpay opens → Pay via PhonePe → Confetti! → Dynamic QR pass appears → 
30-second countdown timer → Show to bouncer → Green screen → Entry granted! 🎉
```

### Club Owner Journey (Happy Path)
```
Open App → Login with +91 → Default guest view → Tap "Claim Your Club" → 
Enter venue claim PIN (from NightVibe sales) → Venue linked → 
Gate Scanner tab opens → See tonight's expected guests list → 
Guest arrives → Shows QR → Camera scans → Green screen with guest details → 
Verify perks (free shooter ✓, queue jump ✓) → Tap "Grant Entry" → 
Escrow settled → PR commission released → Occupancy counter +1 → 
Dashboard shows 247/600 (41% full) → PR leaderboard shows Arjun at #1 with 45 pax
```

### PR Promoter Journey (Happy Path)
```
Open App → Login with +91 → Default guest view → Tap "Become a Verified PR" → 
Enter Instagram handle, niche, city, UPI ID → Submit portfolio → 
"Verification pending" screen → 24h later: verified notification → 
PR Console unlocked → See tonight's authorized events → 
Select "Sunburn Arena" → Set bid price ₹1,700 (floor: ₹1,400) → 
Bundle perks: free shooter + queue jump → See commission estimate: ₹392/pax → 
Publish bid → Bid goes live → Guest books through my link → 
Guest scans at door → "₹392 credited to arjun@okhdfcbank!" notification → 
Wallet shows ₹1,568 (4 pax × ₹392) → Tap "Instant UPI Withdrawal" → 
Money in bank in 60 seconds → Tier upgraded: Rising Star → Silver 🎉
```

---

*Review completed by the Elite Product & Architecture Review Panel. All code examples are production-intent and should be adapted to the specific deployment environment.*
