.class public final Lcom/wukong/manager/cw;
.super Landroid/content/BroadcastReceiver;
.source "SourceFile"


# virtual methods
.method public final onReceive(Landroid/content/Context;Landroid/content/Intent;)V
    .registers 4

    if-eqz p2, :cond_19

    .line 23
    sget-object p1, Lcom/wukong/manager/WukongHmaPolicyBridge;->i:Ljava/lang/String;

    .line 932
    invoke-virtual {p2}, Landroid/content/Intent;->getAction()Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p1, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result p1

    if-nez p1, :cond_f

    goto :goto_19

    .line 935
    :cond_f
    invoke-virtual {p2}, Landroid/content/Intent;->getExtras()Landroid/os/Bundle;

    move-result-object p1

    if-nez p1, :cond_16

    goto :goto_19

    .line 23
    :cond_16
    invoke-static {p1}, Lcom/wukong/manager/WukongHmaPolicyBridge;->e(Landroid/os/Bundle;)V

    :cond_19
    :goto_19
    return-void
.end method
