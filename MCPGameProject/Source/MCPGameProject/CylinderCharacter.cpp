#include "CylinderCharacter.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Materials/MaterialInterface.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "GameFramework/SpringArmComponent.h"
#include "UObject/ConstructorHelpers.h"

ACylinderCharacter::ACylinderCharacter()
{
	GetCapsuleComponent()->InitCapsuleSize(42.f, 96.f);

	// Use the inherited GetMesh() component for the rigged succubus skeletal mesh.
	// This is the correct slot: ACharacter's built-in SkeletalMeshComponent that
	// animation blueprints, IK, and blendspaces all attach to.
	USkeletalMeshComponent* SkelMesh = GetMesh();

	// The FBX skeleton uses Blender's Y-up export convention; Interchange re-axes to Z-up.
	// Capsule half-height = 96 cm. If the Blender root bone is at pelvis/waist, use 0 to -20.
	// Use -96 only when the root bone is exactly at the feet (UE5 mannequin convention).
	// Raise (less negative) if sinking; lower (more negative) if floating.
	SkelMesh->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -35.f), FRotator(0.f, -90.f, 0.f));
	SkelMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	// Load the Blender-rigged skeletal mesh (Content/Characters/Succubus/SK_Succubus.uasset)
	static ConstructorHelpers::FObjectFinder<USkeletalMesh> SuccubusMesh(
		TEXT("/Game/Characters/Succubus/SK_Succubus"));
	if (SuccubusMesh.Succeeded())
	{
		SkelMesh->SetSkeletalMesh(SuccubusMesh.Object);
	}

	// Apply the direct PBR material (M_SK_Succubus_Direct) created by the MCP assign_material
	// command with use_direct=True. UMaterial derives from UMaterialInterface so the finder works.
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> SuccubusMat(
		TEXT("/Game/Characters/Succubus/M_SK_Succubus_Direct"));
	if (SuccubusMat.Succeeded())
	{
		SkelMesh->SetMaterial(0, SuccubusMat.Object);
	}

	// Load the animation blueprint (created by import_succubus_skeletal.py).
	// If it doesn't exist yet, leave blank — character renders in T-pose.
	static ConstructorHelpers::FClassFinder<UAnimInstance> SuccubusABP(
		TEXT("/Game/Characters/Succubus/ABP_Succubus"));
	if (SuccubusABP.Succeeded())
	{
		SkelMesh->SetAnimInstanceClass(SuccubusABP.Class);
	}

	// Spring arm — follows controller rotation so Q/R (yaw input) orbits the camera
	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = 300.f;
	CameraBoom->bUsePawnControlRotation = true;
	CameraBoom->SocketOffset = FVector(0.f, 70.f, 60.f);

	// Camera — inherits spring arm orientation
	FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
	FollowCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	FollowCamera->bUsePawnControlRotation = false;

	// Character turns to face movement direction; camera orbits independently
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw   = false;
	bUseControllerRotationRoll  = false;

	GetCharacterMovement()->bOrientRotationToMovement = true;
	GetCharacterMovement()->RotationRate              = FRotator(0.f, 540.f, 0.f);
	GetCharacterMovement()->JumpZVelocity             = 600.f;
	GetCharacterMovement()->AirControl                = 0.2f;
}

void ACylinderCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	PlayerInputComponent->BindAxis(TEXT("MoveForward"), this, &ACylinderCharacter::MoveForward);
	PlayerInputComponent->BindAxis(TEXT("MoveRight"),   this, &ACylinderCharacter::MoveRight);
	PlayerInputComponent->BindAxis(TEXT("Turn"),        this, &ACylinderCharacter::Turn);

	PlayerInputComponent->BindAction(TEXT("Jump"), IE_Pressed,  this, &ACharacter::Jump);
	PlayerInputComponent->BindAction(TEXT("Jump"), IE_Released, this, &ACharacter::StopJumping);
}

void ACylinderCharacter::MoveForward(float Value)
{
	if (Controller && Value != 0.f)
	{
		const FRotator YawRotation(0.f, Controller->GetControlRotation().Yaw, 0.f);
		AddMovementInput(FRotationMatrix(YawRotation).GetUnitAxis(EAxis::X), Value);
	}
}

void ACylinderCharacter::MoveRight(float Value)
{
	if (Controller && Value != 0.f)
	{
		const FRotator YawRotation(0.f, Controller->GetControlRotation().Yaw, 0.f);
		AddMovementInput(FRotationMatrix(YawRotation).GetUnitAxis(EAxis::Y), Value);
	}
}

void ACylinderCharacter::Turn(float Value)
{
	AddControllerYawInput(Value);
}
