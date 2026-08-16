import React from 'react';
import { Button } from './ui/Button';
import { IconButton } from './ui/IconButton';
import { Badge } from './ui/Badge';
import { Spinner } from './ui/Spinner';
import { Skeleton } from './ui/Skeleton';
import { Kbd } from './ui/Kbd';
import { Separator } from './ui/Separator';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/Tabs';
import { ScrollArea } from './ui/ScrollArea';
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator } from './ui/DropdownMenu';
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/Dialog';
import { ContextMenu, ContextMenuTrigger, ContextMenuContent, ContextMenuItem, ContextMenuSeparator } from './ui/ContextMenu';
import { ToastProvider, ToastViewport, Toast, ToastTitle, ToastDescription, ToastAction } from './ui/Toast';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from './ui/Resizable';
import { Info } from 'lucide-react';

export const KitchenSink = () => {
  const [openToast, setOpenToast] = React.useState(false);

  return (
    <ToastProvider>
      <div className="min-h-screen bg-surface-0 text-text-primary p-8 font-ui">
        <h1 className="text-2xl font-bold mb-8">Primitive Kitchen Sink</h1>
        
        <div className="space-y-12">
          {/* Buttons */}
          <section className="space-y-4">
            <h2 className="text-lg font-semibold border-b border-border-subtle pb-2">Buttons</h2>
            <div className="flex items-center gap-4 flex-wrap">
              <Button variant="primary">Primary</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="danger">Danger</Button>
              <Button variant="primary" disabled>Disabled</Button>
              <Button size="sm">Small</Button>
              <IconButton tooltip="Information">
                <Info size={14} />
              </IconButton>
            </div>
          </section>

          {/* Badges & Indicators */}
          <section className="space-y-4">
            <h2 className="text-lg font-semibold border-b border-border-subtle pb-2">Badges & Indicators</h2>
            <div className="flex items-center gap-4">
              <Badge>Default</Badge>
              <Badge variant="success">Success</Badge>
              <Badge variant="warning">Warning</Badge>
              <Badge variant="danger">Danger</Badge>
              <Badge variant="outline">Outline</Badge>
              <Spinner size="md" />
              <Kbd>⌘K</Kbd>
            </div>
            <div className="w-64">
              <Skeleton className="h-4 w-full mb-2" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          </section>

          {/* Overlays */}
          <section className="space-y-4">
            <h2 className="text-lg font-semibold border-b border-border-subtle pb-2">Overlays (Radix)</h2>
            <div className="flex items-center gap-4">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button>Open Dropdown</Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  <DropdownMenuItem>Profile</DropdownMenuItem>
                  <DropdownMenuItem>Billing</DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem disabled>Settings (disabled)</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <Dialog>
                <DialogTrigger asChild>
                  <Button>Open Dialog</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Edit profile</DialogTitle>
                    <DialogDescription>
                      Make changes to your profile here. Click save when you're done.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="flex justify-end pt-4">
                    <Button variant="primary">Save changes</Button>
                  </div>
                </DialogContent>
              </Dialog>

              <ContextMenu>
                <ContextMenuTrigger className="flex h-[40px] w-[200px] items-center justify-center rounded-md border border-dashed border-border-strong text-sm">
                  Right click here
                </ContextMenuTrigger>
                <ContextMenuContent>
                  <ContextMenuItem>Back</ContextMenuItem>
                  <ContextMenuItem>Forward</ContextMenuItem>
                  <ContextMenuItem>Reload</ContextMenuItem>
                  <ContextMenuSeparator />
                  <ContextMenuItem>Save As...</ContextMenuItem>
                </ContextMenuContent>
              </ContextMenu>

              <Button onClick={() => setOpenToast(true)}>Show Toast</Button>
            </div>
          </section>

          {/* Layout */}
          <section className="space-y-4">
            <h2 className="text-lg font-semibold border-b border-border-subtle pb-2">Layout & Data</h2>
            
            <div className="h-48 w-full max-w-md border border-border-default rounded-md">
              <ResizablePanelGroup direction="horizontal">
                <ResizablePanel defaultSize={30} className="flex items-center justify-center bg-surface-1">
                  Sidebar
                </ResizablePanel>
                <ResizableHandle withHandle />
                <ResizablePanel defaultSize={70} className="flex items-center justify-center bg-surface-0">
                  Content
                </ResizablePanel>
              </ResizablePanelGroup>
            </div>

            <Separator className="my-8" />

            <Tabs defaultValue="account" className="w-[400px]">
              <TabsList className="w-full justify-start">
                <TabsTrigger value="account">Account</TabsTrigger>
                <TabsTrigger value="password">Password</TabsTrigger>
              </TabsList>
              <TabsContent value="account" className="p-4 bg-surface-1 rounded-md mt-2">
                Account settings...
              </TabsContent>
              <TabsContent value="password" className="p-4 bg-surface-1 rounded-md mt-2">
                Change password...
              </TabsContent>
            </Tabs>

            <ScrollArea className="h-32 w-64 rounded-md border border-border-default bg-surface-1 p-4">
              <div className="pr-4">
                <h4 className="mb-4 text-sm font-medium leading-none">Tags</h4>
                {Array.from({ length: 20 }).map((_, i) => (
                  <div key={i} className="text-sm">
                    Tag {i}
                    <Separator className="my-2" />
                  </div>
                ))}
              </div>
            </ScrollArea>
          </section>
        </div>

        <Toast open={openToast} onOpenChange={setOpenToast}>
          <div className="grid gap-1">
            <ToastTitle>Scheduled: Catch up</ToastTitle>
            <ToastDescription>Friday, February 10, 2023 at 5:57 PM</ToastDescription>
          </div>
          <ToastAction altText="Undo">Undo</ToastAction>
        </Toast>
        <ToastViewport />
      </div>
    </ToastProvider>
  );
};
