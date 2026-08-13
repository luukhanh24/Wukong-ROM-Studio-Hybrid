.class public abstract synthetic Lcom/wukong/manager/cu;
.super Ljava/lang/Object;
.source "SourceFile"


# direct methods
.method public static bridge synthetic e(Landroid/content/Context;)Ljava/lang/String;
    .registers 1

    invoke-virtual {p0}, Landroid/content/Context;->getOpPackageName()Ljava/lang/String;

    move-result-object p0

    return-object p0
.end method
