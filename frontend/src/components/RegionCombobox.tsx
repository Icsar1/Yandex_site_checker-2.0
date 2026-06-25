import { useEffect, useId, useState } from "react";
import { Check, Loader2, MapPin, Search } from "lucide-react";

import { getRegions, type Region } from "@/api/client";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverAnchor,
  PopoverContent,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

interface RegionComboboxProps {
  value: Region | null;
  onChange: (region: Region | null) => void;
  placeholder?: string;
}

export function RegionCombobox({
  value,
  onChange,
  placeholder = "Москва, Санкт-Петербург...",
}: RegionComboboxProps) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value?.name ?? "");
  const [regions, setRegions] = useState<Region[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setQuery(value?.name ?? "");
  }, [value?.id, value?.name]);

  useEffect(() => {
    let active = true;
    const timeoutId = window.setTimeout(async () => {
      try {
        setLoading(true);
        const nextRegions = await getRegions(query);

        if (!active) {
          return;
        }

        setRegions(nextRegions);
        setError(null);
      } catch (caught) {
        if (!active) {
          return;
        }

        setRegions([]);
        setError(
          caught instanceof Error ? caught.message : "Не удалось найти регион",
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }, 300);

    return () => {
      active = false;
      window.clearTimeout(timeoutId);
    };
  }, [query]);

  const selectRegion = (region: Region) => {
    onChange(region);
    setQuery(region.name);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            role="combobox"
            aria-label="Регион"
            aria-expanded={open}
            aria-controls={listId}
            value={query}
            placeholder={placeholder}
            className="pl-9 pr-10"
            onFocus={() => setOpen(true)}
            onChange={(event) => {
              const nextValue = event.target.value;
              setQuery(nextValue);
              setOpen(true);
              if (value && nextValue !== value.name) {
                onChange(null);
              }
            }}
          />
          <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <MapPin className="h-4 w-4" />
            )}
          </div>
        </div>
      </PopoverAnchor>
      <PopoverContent
        align="start"
        className="w-[min(28rem,calc(100vw-2rem))] p-0"
        onOpenAutoFocus={(event) => event.preventDefault()}
      >
        <Command id={listId}>
          <CommandList>
            {error ? <CommandEmpty>{error}</CommandEmpty> : null}
            {!error && !loading && regions.length === 0 ? (
              <CommandEmpty>Регион не найден</CommandEmpty>
            ) : null}
            <CommandGroup>
              {regions.map((region) => (
                <CommandItem
                  key={region.id}
                  onClick={() => selectRegion(region)}
                  className="justify-between"
                >
                  <span>{region.name}</span>
                  <Check
                    className={cn(
                      "h-4 w-4",
                      value?.id === region.id ? "opacity-100" : "opacity-0",
                    )}
                  />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
