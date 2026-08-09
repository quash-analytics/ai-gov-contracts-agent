"""Entrypoints — installed as the `jarvis` command (and `python -m jarvis`):

  jarvis                       chat in the terminal (default)
  jarvis dashboard             the browser cockpit → localhost:7777 (+ Telegram if configured)
  jarvis connections           list configured integrations and their health
  jarvis voice                 talk to it (needs the [voice] extra)
  jarvis telegram              phone → laptop (needs TELEGRAM_BOT_TOKEN)
  jarvis discord               Discord → laptop (needs DISCORD_BOT_TOKEN)
  jarvis whatsapp              WhatsApp → laptop (needs WHATSAPP_TOKEN, public URL)
  jarvis brief                 morning briefing (calendar + mail + memory) — as a LOOP
  jarvis gather                same job as a GRAPH: github, web, calendar and
                             memory fetched together, then one digest
  jarvis skill install <url>   install a community skill
"""

from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    if not args:
        from jarvis.gateway.cli import main as cli_main

        cli_main()
    elif args[0] == "dashboard":
        from jarvis.ops.dashboard import main as dash_main

        dash_main()
    elif args[0] == "connections":
        from jarvis.integrations import cli_main

        sys.exit(cli_main())
    elif args[0] == "voice":
        from jarvis.gateway.voice import main as voice_main

        voice_main()
    elif args[0] == "telegram":
        from jarvis.gateway.telegram import main as tg_main

        tg_main()
    elif args[0] == "discord":
        from jarvis.gateway.discord import main as discord_main

        discord_main()
    elif args[0] == "whatsapp":
        from jarvis.gateway.whatsapp import main as wa_main

        wa_main()
    elif args[0] == "brief":
        from jarvis.ops.brief import main as brief_main

        brief_main()
    elif args[0] == "gather":
        from jarvis.ops.gather import main as gather_main

        gather_main()
    elif args[0] == "skill" and len(args) >= 3 and args[1] == "install":
        from jarvis.memory.procedural.installer import install

        install(args[2])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
