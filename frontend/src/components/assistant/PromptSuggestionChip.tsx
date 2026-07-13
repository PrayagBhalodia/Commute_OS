import { Button } from "@/components/ui/button";

export function PromptSuggestionChip({ children, onClick }: { children: string; onClick: () => void }) {
  return (
    <Button type="button" variant="secondary" size="sm" onClick={onClick} className="h-auto justify-start whitespace-normal py-2 text-left">
      {children}
    </Button>
  );
}
