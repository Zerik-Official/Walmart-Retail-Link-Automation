from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)

BANNER: str = (
    f"{Fore.CYAN}{Style.BRIGHT}"
    "\n ██╗    ██╗ █████╗ ██╗     ███╗   ███╗ █████╗ ██████╗ ████████╗"
    "\n ██║    ██║██╔══██╗██║     ████╗ ████║██╔══██╗██╔══██╗╚══██╔══╝"
    "\n ██║ █╗ ██║███████║██║     ██╔████╔██║███████║██████╔╝   ██║   "
    "\n ██║███╗██║██╔══██║██║     ██║╚██╔╝██║██╔══██║██╔══██╗   ██║   "
    "\n ╚███╔███╔╝██║  ██║███████╗██║ ╚═╝ ██║██║  ██║██║  ██║   ██║   "
    "\n  ╚══╝╚══╝ ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   "
    f"{Style.RESET_ALL}"
    f"\n{Fore.GREEN}Walmart Retail Link Automation{Style.RESET_ALL}"
    f"\n{Fore.YELLOW}Version 1.0.0{Style.RESET_ALL}\n"
)

__all__: list[str] = ["BANNER"]
