import Dashboard from "./Dashboard";
import Connect from "./Connect";
import { Toasts } from "./ui";
import { useStore } from "./store";

export default function App() {
  const { cfg, api, disconnect, toast } = useStore();

  if (!cfg || !api) {
    return (
      <>
        <Connect />
        <Toasts />
      </>
    );
  }

  return (
    <>
      <Dashboard
        api={api}
        onDisconnect={() => {
          disconnect();
          toast("Disconnected — keys stay on this device only.", "info");
        }}
      />
      <Toasts />
      <footer className="border-t border-slate-200/70 py-4 text-center text-[11px] text-slate-400 dark:border-slate-800/70">
        Shortly ·{" "}
        <a href="https://github.com/Dani-Devlop/shortly-url" target="_blank" rel="noopener noreferrer" className="hover:text-emerald-500">
          Dani-Devlop/shortly-url
        </a>{" "}
        · press <kbd className="rounded border border-slate-300 px-1 dark:border-slate-700">n</kbd> to create ·{" "}
        <kbd className="rounded border border-slate-300 px-1 dark:border-slate-700">/</kbd> to search
      </footer>
    </>
  );
}
