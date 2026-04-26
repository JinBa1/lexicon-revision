import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CopyLinkButton } from "@/components/source/CopyLinkButton";

const originalClipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, "clipboard");

function mockClipboardWriteText(writeText: ReturnType<typeof vi.fn>) {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();

  if (originalClipboardDescriptor) {
    Object.defineProperty(navigator, "clipboard", originalClipboardDescriptor);
  } else {
    Reflect.deleteProperty(navigator, "clipboard");
  }
});

describe("<CopyLinkButton>", () => {
  it("renders a copy link button with no feedback initially", () => {
    render(<CopyLinkButton url="https://example.test/x" />);

    expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("");
    expect(screen.queryByDisplayValue("https://example.test/x")).not.toBeInTheDocument();
  });

  it("happy path: writes to clipboard, shows feedback, then resets", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn().mockResolvedValue(undefined);
    mockClipboardWriteText(writeText);

    render(<CopyLinkButton url="https://example.test/x" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByRole("status")).toHaveTextContent("Link copied");
    expect(writeText).toHaveBeenCalledWith("https://example.test/x");
    expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2_000);
    });

    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("failure path: shows fallback selectable URL input", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    mockClipboardWriteText(writeText);

    render(<CopyLinkButton url="https://example.test/x" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("Copy failed — select URL");
    });
    const input = screen.getByDisplayValue("https://example.test/x");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("readonly");
    expect(screen.getByRole("textbox", { name: /shareable source url/i })).toBe(input);
  });
});
