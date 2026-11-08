"""Writes demo/mbox_en/Inbox.mbox: a sample inbox for the demo (fictional senders, nothing real). Import it in Mail with
File > Import Mailboxes... > Files in mbox format. The parcel email (demo/parcel.eml) sits in the middle of the list. Mail ignores
the read flags of an mbox on import: mark_read() prints the AppleScript that applies them."""
from __future__ import annotations

import email
import email.policy
import mailbox
from email.message import EmailMessage
from pathlib import Path

HERE = Path(__file__).resolve().parent
TO = "Camille Dupont <camille.dupont@example.com>"
MESSAGES = [  # newest first; (date, from, subject, body, read)
    ("Sun, 08 Nov 2026 07:12:00 +0100", "Northline Rail <tickets@northline-example.com>", "Your e-ticket: Paris → Lyon on November 12",
     "Hi Camille,\n\nHere is your e-ticket for Thursday, November 12, 2026.\n\nParis Gare de Lyon 08:04 → Lyon Part-Dieu 10:02\nCoach 14, seat 82\nBooking reference: QXRT7L\n\nHave a good trip!\nNorthline Rail", False),
    ("Sun, 08 Nov 2026 06:48:00 +0100", "The Morning Brief <news@morningbrief-example.com>", "COP31, the 2027 budget and three ideas for the weekend",
     "Good morning,\n\nWhat matters today: the COP31 talks on forests, the 2027 budget vote, and three short trips for the weekend.\n\nThe Morning Brief", False),
    ("Sat, 07 Nov 2026 18:22:00 +0100", "Julie Martin <julie.martin@example.com>", "Dinner next Saturday?",
     "Hi! Are you free for dinner next Saturday, the 14th? We wanted to try the little Lebanese place on rue Mercière. Let me know and I'll book for four.\n\nJulie", False),
    ("Sat, 07 Nov 2026 16:03:00 +0100", "Thomas Bernard <thomas.bernard@example.com>", "Slides for Monday's meeting",
     "Hi Camille,\n\nI put the slides for the team meeting on the drive. Could you read the budget part before Monday? Nothing urgent.\n\nThanks,\nThomas", True),
    ("Sat, 07 Nov 2026 11:30:00 +0100", "Second Hand <no-reply@secondhand-example.com>", "Your item has been sold 🎉",
     "Good news! Your denim jacket, size M, was bought for €25.00. Ship it before November 12 to get paid.\n\nSecond Hand", True),
    ("Fri, 06 Nov 2026 09:15:00 +0100", "CityCare <reminders@citycare-example.com>", "Reminder: appointment with Dr Lefèvre on Monday, November 9",
     "Hello Camille Dupont,\n\nThis is a reminder of your appointment with Dr Lefèvre, general practitioner, on Monday, November 9, 2026 at 9:30.\n\nCityCare", True),
    ("Thu, 05 Nov 2026 10:00:00 +0100", "Homeline Fibre <billing@homeline-example.com>", "Your November bill is available",
     "Hello,\n\nYour November 2026 bill is available in your account. Amount: €39.99 including tax, charged on November 15.\n\nHomeline Fibre", True),
    ("Wed, 04 Nov 2026 19:44:00 +0100", "Swap Street <messages@swapstreet-example.com>", "New message about your city bike",
     "You have a new message: \"Hello, is the bike still available? I can come by tomorrow around 6 pm.\"\n\nSwap Street", False),
    ("Sun, 01 Nov 2026 12:05:00 +0100", "Stayaway <trips@stayaway-example.com>", "Your stay in Annecy is coming up",
     "Hi Camille,\n\nYour stay at Marc's place starts in three weeks. Check-in is from 4 pm.\n\nStayaway", True),
]
OLDER = [  # older than the parcel email, so the list runs past the bottom of the screen; (date, from, subject, body, read)
    ("Mon, 19 Oct 2026 20:05:00 +0200", "Sophie Lambert <sophie.lambert@example.com>", "Photos from the weekend",
     "Hi Camille,\n\nHere's the album from Sunday. The one on the bridge is my favourite.\n\nSophie", True),
    ("Sun, 18 Oct 2026 09:32:00 +0200", "The Morning Brief <news@morningbrief-example.com>", "Sunday edition: a long read on night trains",
     "Good morning,\n\nThis week: why night trains are coming back, and where they go next.\n\nThe Morning Brief", False),
    ("Thu, 15 Oct 2026 17:48:00 +0200", "Thomas Bernard <thomas.bernard@example.com>", "Team lunch on Friday",
     "Hi all,\n\nI booked a table for six at 12:30 on Friday. Tell me if you can't make it.\n\nThomas", True),
    ("Mon, 12 Oct 2026 08:10:00 +0200", "Homeline Fibre <billing@homeline-example.com>", "Your October bill is available",
     "Hello,\n\nYour October 2026 bill is available in your account. Amount: €39.99 including tax, charged on October 15.\n\nHomeline Fibre", True),
    ("Fri, 09 Oct 2026 12:00:00 +0200", "Book Corner <hello@bookcorner-example.com>", "Three novels we loved this month",
     "Hello Camille,\n\nOur booksellers picked three novels for the autumn. Come and browse them in the shop.\n\nBook Corner", False),
    ("Mon, 05 Oct 2026 21:17:00 +0200", "Julie Martin <julie.martin@example.com>", "Housewarming on the 24th!",
     "We finally moved in! Come over on Saturday the 24th from 7 pm. Bring nothing but yourself.\n\nJulie", True),
    ("Thu, 01 Oct 2026 10:26:00 +0200", "Northline Rail <tickets@northline-example.com>", "Your loyalty points expire soon",
     "Hi Camille,\n\nYou have 1,240 points left, valid until December 31.\n\nNorthline Rail", True),
    ("Sun, 27 Sep 2026 15:40:00 +0200", "Stayaway <trips@stayaway-example.com>", "Your stay in Annecy is confirmed",
     "Hi Camille,\n\nMarc accepted your request. See you in November!\n\nStayaway", True),
]


def add(box: mailbox.mbox, messages: list[tuple]) -> None:
    for date, sender, subject, body, read in messages:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"], msg["Date"] = sender, TO, subject, date
        msg["Message-ID"] = "<" + date.replace(" ", "").replace(":", "").replace(",", "") + "@example.com>"
        if read:
            msg["Status"] = "RO"
        msg.set_content(body)
        box.add(msg)


def main() -> None:
    path = HERE / "Inbox.mbox"
    path.unlink(missing_ok=True)
    box = mailbox.mbox(path)
    add(box, MESSAGES)
    parcel = email.message_from_bytes((HERE.parent / "parcel.eml").read_bytes(), policy=email.policy.default)
    parcel["Status"] = "RO"
    box.add(parcel)
    add(box, OLDER)
    box.flush()
    box.close()
    print(path, path.stat().st_size)


def mark_read() -> str:
    """AppleScript for Mail: the imported messages come in unread."""
    parcel = email.message_from_bytes((HERE.parent / "parcel.eml").read_bytes(), policy=email.policy.default)
    read = [subject for _d, _f, subject, _b, was_read in MESSAGES + OLDER if was_read] + [str(parcel["Subject"])]
    names = ", ".join('"' + subject.replace('"', '\\"') + '"' for subject in read)
    return f'tell application "Mail" to repeat with m in messages of mailbox "Import/Inbox"\nset read status of m to ({{{names}}} contains subject of m)\nend repeat'


if __name__ == "__main__":
    main()
